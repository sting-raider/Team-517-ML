#!/usr/bin/env python3
"""X013: same-country Source-1 adversarial train-vs-test shift audit.

Uses only business_name, business_address, country, and split membership.
Record IDs and match labels are never read as predictive evidence.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

COUNTRIES = ("US", "India")
USECOLS = ["business_name", "business_address", "country"]


def normalize_series(s: pd.Series) -> pd.Series:
    """Semantic mirror of lower(strip_accents()) + non-letter/non-number collapse."""
    return (
        s.astype(str)
        .str.normalize("NFKD")
        .str.replace(r"[\u0300-\u036f]", "", regex=True)
        .str.lower()
        .str.replace(r"[\W_]+", " ", regex=True)
        .str.strip()
    )


def grouped_fold(country: pd.Series, joint: pd.Series, salt: str = "x013split") -> np.ndarray:
    """Assign identical normalized country+joint text to the same deterministic fold."""
    key = salt + "\x1f" + country.astype(str) + "\x1f" + joint.astype(str)
    return (pd.util.hash_pandas_object(key, index=False).to_numpy(dtype="uint64") % 5).astype("uint8")


def scan_population(path: Path, chunksize: int = 100_000) -> dict:
    out: dict[str, dict] = {}
    for chunk in pd.read_csv(
        path, sep="\t", usecols=USECOLS, dtype=str, keep_default_na=False, chunksize=chunksize
    ):
        for country, g in chunk.groupby("country", sort=False):
            n = len(g)
            name = g["business_name"]
            addr = g["business_address"]
            d = out.setdefault(
                country,
                {
                    "n": 0,
                    "name_chars": 0,
                    "addr_chars": 0,
                    "empty_name": 0,
                    "empty_addr": 0,
                    "name_digits": 0,
                    "addr_digits": 0,
                    "name_nonascii": 0,
                    "addr_nonascii": 0,
                },
            )
            d["n"] += n
            d["name_chars"] += int(name.str.len().sum())
            d["addr_chars"] += int(addr.str.len().sum())
            d["empty_name"] += int((name.str.len() == 0).sum())
            d["empty_addr"] += int((addr.str.len() == 0).sum())
            d["name_digits"] += int(name.str.count(r"\d").sum())
            d["addr_digits"] += int(addr.str.count(r"\d").sum())
            d["name_nonascii"] += int(name.str.count(r"[^\x00-\x7F]").sum())
            d["addr_nonascii"] += int(addr.str.count(r"[^\x00-\x7F]").sum())
    summary = {}
    for country, d in out.items():
        n = d["n"]
        summary[country] = {
            "n": n,
            "avg_name_len": d["name_chars"] / n,
            "avg_addr_len": d["addr_chars"] / n,
            "empty_name_rate": d["empty_name"] / n,
            "empty_addr_rate": d["empty_addr"] / n,
            "name_digits_per_row": d["name_digits"] / n,
            "addr_digits_per_row": d["addr_digits"] / n,
            "name_nonascii_per_row": d["name_nonascii"] / n,
            "addr_nonascii_per_row": d["addr_nonascii"] / n,
        }
    return summary


def deterministic_sample(
    path: Path, domain: str, sample_per_country: int, salt: str, chunksize: int = 100_000
) -> pd.DataFrame:
    """Keep the smallest deterministic text hashes per country; IDs are never loaded."""
    states: dict[str, pd.DataFrame] = {}
    for chunk in pd.read_csv(
        path, sep="\t", usecols=USECOLS, dtype=str, keep_default_na=False, chunksize=chunksize
    ):
        chunk = chunk[chunk["country"].isin(COUNTRIES)].copy()
        if chunk.empty:
            continue
        key = (
            salt
            + "\x1f"
            + chunk["country"]
            + "\x1f"
            + chunk["business_name"]
            + "\x1f"
            + chunk["business_address"]
        )
        chunk["_sample_hash"] = pd.util.hash_pandas_object(key, index=False).to_numpy(dtype="uint64")
        for country, g in chunk.groupby("country", sort=False):
            g = g[["_sample_hash", "business_name", "business_address", "country"]]
            if country in states:
                g = pd.concat([states[country], g], ignore_index=True)
            if len(g) > sample_per_country:
                idx = np.argpartition(g["_sample_hash"].to_numpy(), sample_per_country - 1)[
                    :sample_per_country
                ]
                g = g.iloc[idx].copy()
            states[country] = g
    frames = []
    for country, g in states.items():
        g = g.sort_values("_sample_hash").reset_index(drop=True)
        frames.append(g.assign(domain=domain))
    return pd.concat(frames, ignore_index=True)


def prepare_sample(train_path: Path, test_path: Path, n: int, salt: str) -> pd.DataFrame:
    df = pd.concat(
        [
            deterministic_sample(train_path, "train", n, salt),
            deterministic_sample(test_path, "test", n, salt),
        ],
        ignore_index=True,
    )
    df["n_name"] = normalize_series(df["business_name"])
    df["n_addr"] = normalize_series(df["business_address"])
    df["joint"] = (df["n_name"] + " " + df["n_addr"]).str.strip()
    df["_fold"] = grouped_fold(df["country"], df["joint"], salt=salt + "-fold")
    df["y"] = (df["domain"] == "test").astype("int8")
    return df


def structural_matrix(df: pd.DataFrame) -> np.ndarray:
    name, addr = df["business_name"], df["business_address"]
    nn, aa = df["n_name"], df["n_addr"]
    x = pd.DataFrame(
        {
            "raw_name_len": name.str.len(),
            "raw_addr_len": addr.str.len(),
            "norm_name_len": nn.str.len(),
            "norm_addr_len": aa.str.len(),
            "name_tokens": nn.str.count(" ") + 1,
            "addr_tokens": aa.str.count(" ") + 1,
            "name_digits": name.str.count(r"\d"),
            "addr_digits": addr.str.count(r"\d"),
            "name_spaces": name.str.count(" "),
            "addr_spaces": addr.str.count(" "),
            "name_commas": name.str.count(","),
            "addr_commas": addr.str.count(","),
            "name_hyphens": name.str.count("-"),
            "addr_hyphens": addr.str.count("-"),
            "name_slashes": name.str.count("/"),
            "addr_slashes": addr.str.count("/"),
            "name_periods": name.str.count(r"\."),
            "addr_periods": addr.str.count(r"\."),
            "name_parens": name.str.count(r"[\(\)]"),
            "addr_parens": addr.str.count(r"[\(\)]"),
            "name_nonascii": name.str.count(r"[^\x00-\x7F]"),
            "addr_nonascii": addr.str.count(r"[^\x00-\x7F]"),
        }
    )
    return x.to_numpy(dtype=np.float32)


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "auroc": float(roc_auc_score(y, p)),
        "auprc": float(average_precision_score(y, p)),
        "balanced_accuracy": float(balanced_accuracy_score(y, p >= 0.5)),
    }


def run_sample(df: pd.DataFrame, seed: int = 517, include_views: bool = True) -> dict:
    out = {}
    for country in COUNTRIES:
        d = df[df["country"] == country]
        tr, ev = d["_fold"] != 0, d["_fold"] == 0
        ytr, yev = d.loc[tr, "y"].to_numpy(), d.loc[ev, "y"].to_numpy()
        cres = {
            "n_train": int(tr.sum()),
            "n_eval": int(ev.sum()),
            "eval_prevalence": float(yev.mean()),
        }

        sxtr, sxev = structural_matrix(d.loc[tr]), structural_matrix(d.loc[ev])
        structural = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=500, class_weight="balanced", random_state=seed),
        )
        structural.fit(sxtr, ytr)
        cres["structural"] = metrics(yev, structural.predict_proba(sxev)[:, 1])

        views = (("name", "n_name"), ("address", "n_addr"), ("joint", "joint"))
        if not include_views:
            views = (("joint", "joint"),)
        for view, col in views:
            vec = HashingVectorizer(
                analyzer="char",
                ngram_range=(3, 5),
                n_features=2**18,
                alternate_sign=False,
                norm="l2",
                lowercase=False,
            )
            xtr = vec.transform(d.loc[tr, col].tolist())
            xev = vec.transform(d.loc[ev, col].tolist())
            clf = SGDClassifier(
                loss="log_loss",
                alpha=1e-6,
                max_iter=20,
                tol=1e-4,
                class_weight="balanced",
                random_state=seed,
                average=True,
            )
            clf.fit(xtr, ytr)
            cres[view] = metrics(yev, clf.predict_proba(xev)[:, 1])
            if view == "joint":
                rng = np.random.default_rng(seed)
                ysh = ytr.copy()
                rng.shuffle(ysh)
                null = SGDClassifier(
                    loss="log_loss",
                    alpha=1e-6,
                    max_iter=20,
                    tol=1e-4,
                    class_weight="balanced",
                    random_state=seed + 1,
                    average=True,
                )
                null.fit(xtr, ysh)
                cres["joint_label_shuffle_null"] = metrics(
                    yev, null.predict_proba(xev)[:, 1]
                )
        out[country] = cres
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train-source1", type=Path, required=True)
    p.add_argument("--test-source1", type=Path, required=True)
    p.add_argument("--sample-per-domain-country", type=int, default=60_000)
    p.add_argument("--replication-sample", type=int, default=30_000)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    started = time.time()
    result = {
        "experiment_id": "X013",
        "population": {
            "train": scan_population(args.train_source1),
            "test": scan_population(args.test_source1),
        },
        "protocol": {
            "primary_sample_per_domain_country": args.sample_per_domain_country,
            "replication_sample_per_domain_country": args.replication_sample,
            "grouped_eval_fold": 0,
            "folds": 5,
            "char_ngrams": [3, 5],
            "hash_features": 2**18,
            "seed": 517,
            "id_features": False,
        },
    }
    primary = prepare_sample(
        args.train_source1, args.test_source1, args.sample_per_domain_country, "x013-primary"
    )
    result["primary"] = run_sample(primary, seed=517, include_views=True)
    replica = prepare_sample(
        args.train_source1, args.test_source1, args.replication_sample, "x013-rep2"
    )
    result["replication"] = run_sample(replica, seed=717, include_views=False)
    result["runtime_seconds"] = time.time() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
