"""R030: Source-1 character n-gram cardinality-prior feasibility.

Uses complete Source-1 + supplied ground truth for population/split construction.
Record IDs are used only for fold517 assignment and label joins, never as features.
The classifier gate is a deterministic Tier-1 sample.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.svm import LinearSVC


def truth_cardinality(value: str) -> int:
    if not value:
        return 0
    return sum(bool(x.strip()) for x in str(value).split(","))


def fold_bucket(entity_id: str) -> int:
    return int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100


def normalize_name_series(series: pd.Series) -> pd.Series:
    return (
        series.fillna("").astype(str).str.lower()
        .str.replace(r"_", " ", regex=True)
        .str.replace(r"[^\w]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def split_masks(bucket: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "fit": bucket < 60,
        "early": (bucket >= 60) & (bucket < 75),
        "calibrate": (bucket >= 75) & (bucket < 90),
        "holdout": bucket >= 90,
    }


def deterministic_sample(indices: np.ndarray, n: int, seed: int) -> np.ndarray:
    if len(indices) <= n:
        return indices.copy()
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(indices, size=n, replace=False))


def binary_metrics(y: np.ndarray, score: np.ndarray, probability: np.ndarray | None = None) -> dict:
    y = np.asarray(y, dtype=np.uint8)
    score = np.asarray(score, dtype=float)
    prevalence = float(y.mean())
    out = {
        "n": int(len(y)),
        "positive_count": int(y.sum()),
        "prevalence": prevalence,
        "auroc": float(roc_auc_score(y, score)),
        "auprc": float(average_precision_score(y, score)),
    }
    if probability is not None:
        p = np.asarray(probability, dtype=float)
        eps = 1e-12
        constant = np.full(len(y), prevalence)
        out.update({
            "brier": float(brier_score_loss(y, p)),
            "constant_brier": float(brier_score_loss(y, constant)),
            "logloss": float(log_loss(y, np.clip(p, eps, 1 - eps), labels=[0, 1])),
            "constant_logloss": float(log_loss(y, np.clip(constant, eps, 1 - eps), labels=[0, 1])),
        })
    return out


def targeting_metrics(y: np.ndarray, score: np.ndarray, fractions=(.01, .025, .05, .10, .20)) -> dict:
    y = np.asarray(y, dtype=np.uint8)
    score = np.asarray(score, dtype=float)
    order = np.argsort(-score, kind="mergesort")
    positives = int(y.sum())
    prevalence = float(y.mean())
    out = {}
    for frac in fractions:
        k = max(1, int(round(len(y) * frac)))
        tp = int(y[order[:k]].sum())
        precision = tp / k
        out[str(frac)] = {
            "selected": k,
            "precision": precision,
            "recall": tp / positives if positives else None,
            "lift": precision / prevalence if prevalence else None,
        }
    return out


def load_population(source1_path: Path, truth_path: Path) -> pd.DataFrame:
    s1 = pd.read_csv(
        source1_path, sep="\t", dtype=str, keep_default_na=False,
        usecols=["entity_id", "business_name", "country"],
    )
    truth = pd.read_csv(
        truth_path, sep="\t", dtype=str, keep_default_na=False,
        usecols=["source1_entity_id", "matched_entity_ids"],
    )
    if len(s1) != len(truth):
        raise ValueError("Source-1 / truth row-count mismatch")
    if s1["entity_id"].duplicated().any() or truth["source1_entity_id"].duplicated().any():
        raise ValueError("duplicate Source-1 IDs")
    truth["cardinality"] = truth["matched_entity_ids"].map(truth_cardinality).astype(np.uint8)
    labels = truth.set_index("source1_entity_id")["cardinality"]
    s1["cardinality"] = s1["entity_id"].map(labels)
    if s1["cardinality"].isna().any():
        raise ValueError("Source-1 / truth ID mismatch")
    s1["cardinality"] = s1["cardinality"].astype(np.uint8)
    s1["name_norm"] = normalize_name_series(s1["business_name"])
    return s1


def build_splits(df: pd.DataFrame) -> tuple[dict, dict]:
    entity_bucket = np.fromiter(
        (fold_bucket(x) for x in df["entity_id"]), dtype=np.uint8, count=len(df)
    )
    # Exact measured R030 runtime used pandas 2.2.3 hashing on normalized text.
    family_bucket = (
        pd.util.hash_pandas_object(df["name_norm"], index=False)
        .to_numpy(dtype=np.uint64) % 100
    )
    entity_masks, family_masks = split_masks(entity_bucket), split_masks(family_bucket)
    fit_fams = set(df.loc[family_masks["fit"], "name_norm"].unique())
    hold_fams = set(df.loc[family_masks["holdout"], "name_norm"].unique())
    if fit_fams & hold_fams:
        raise AssertionError("family split leaked an exact normalized-name family")
    return entity_masks, family_masks


def vectorizer(n_features: int) -> HashingVectorizer:
    return HashingVectorizer(
        analyzer="char_wb", ngram_range=(3, 4), n_features=n_features,
        alternate_sign=False, norm="l2", lowercase=False, dtype=np.float32,
    )


def run_one(
    df: pd.DataFrame,
    fit_mask: np.ndarray,
    hold_mask: np.ndarray,
    *,
    seed: int,
    train_n: int,
    eval_n: int,
    n_features: int,
    max_iter: int = 20,
) -> dict:
    y = (df["cardinality"].to_numpy() >= 5).astype(np.uint8)
    fit_idx = deterministic_sample(np.flatnonzero(fit_mask), train_n, seed)
    hold_idx = deterministic_sample(np.flatnonzero(hold_mask), eval_n, seed + 10000)
    vec = vectorizer(n_features)
    x_fit = vec.transform(df["name_norm"].iloc[fit_idx])
    x_hold = vec.transform(df["name_norm"].iloc[hold_idx])
    model = SGDClassifier(
        loss="log_loss", alpha=1e-5, penalty="l2", random_state=seed,
        max_iter=max_iter, tol=1e-4 if max_iter <= 20 else 1e-5, average=True,
    )
    model.fit(x_fit, y[fit_idx])
    probability = model.predict_proba(x_hold)[:, 1]
    result = {
        "seed": seed,
        "train_n": int(len(fit_idx)),
        "eval_n": int(len(hold_idx)),
        "metrics": binary_metrics(y[hold_idx], probability, probability),
        "targeting": targeting_metrics(y[hold_idx], probability),
        "country": {},
    }
    countries = df["country"].to_numpy()
    for country in sorted(df["country"].unique()):
        mask = countries[hold_idx] == country
        if mask.any() and len(np.unique(y[hold_idx][mask])) == 2:
            result["country"][country] = binary_metrics(
                y[hold_idx][mask], probability[mask], probability[mask]
            )
    return result


def run_red_team(
    df: pd.DataFrame,
    fit_mask: np.ndarray,
    hold_mask: np.ndarray,
    *,
    seed: int,
    train_n: int,
    eval_n: int,
    n_features: int,
) -> dict:
    y = (df["cardinality"].to_numpy() >= 5).astype(np.uint8)
    fit_idx = deterministic_sample(np.flatnonzero(fit_mask), train_n, seed)
    hold_idx = deterministic_sample(np.flatnonzero(hold_mask), eval_n, seed + 10000)
    vec = vectorizer(n_features)
    x_fit = vec.transform(df["name_norm"].iloc[fit_idx])
    x_hold = vec.transform(df["name_norm"].iloc[hold_idx])
    out = {}
    sgd = SGDClassifier(
        loss="log_loss", alpha=1e-5, random_state=seed,
        max_iter=100, tol=1e-5, average=True,
    ).fit(x_fit, y[fit_idx])
    score = sgd.decision_function(x_hold)
    out["sgd100"] = {
        **binary_metrics(y[hold_idx], score),
        "targeting": targeting_metrics(y[hold_idx], score),
    }
    svm = LinearSVC(C=.1, max_iter=5000, random_state=seed).fit(x_fit, y[fit_idx])
    score = svm.decision_function(x_hold)
    out["linear_svc"] = {
        **binary_metrics(y[hold_idx], score),
        "targeting": targeting_metrics(y[hold_idx], score),
    }
    return out


def run(args) -> dict:
    started = time.time()
    df = load_population(args.source1, args.truth)
    entity_masks, family_masks = build_splits(df)
    y = (df["cardinality"].to_numpy() >= 5)
    entity_fit_fams = set(df.loc[entity_masks["fit"], "name_norm"].unique())
    entity_seen = float(
        df.loc[entity_masks["holdout"], "name_norm"].isin(entity_fit_fams).mean()
    )
    population = {
        "rows": int(len(df)),
        "high_cardinality_count": int(y.sum()),
        "high_cardinality_prevalence": float(y.mean()),
        "cardinality_mean": float(df["cardinality"].mean()),
        "cardinality_max": int(df["cardinality"].max()),
        "entity_split_counts": {k: int(v.sum()) for k, v in entity_masks.items()},
        "family_split_counts": {k: int(v.sum()) for k, v in family_masks.items()},
        "unique_name_families": int(df["name_norm"].nunique()),
        "entity_holdout_fraction_name_family_seen_in_entity_fit": entity_seen,
        "family_fit_holdout_overlap": 0,
        "country": {
            country: {
                "n": int((df["country"] == country).sum()),
                "high_cardinality_prevalence": float(
                    y[df["country"].to_numpy() == country].mean()
                ),
            }
            for country in sorted(df["country"].unique())
        },
    }
    runs = []
    for seed in args.seeds:
        runs.append({
            "split": "entity",
            **run_one(
                df, entity_masks["fit"], entity_masks["holdout"],
                seed=seed, train_n=args.train_n, eval_n=args.eval_n,
                n_features=args.n_features,
            ),
        })
    for seed in args.seeds:
        runs.append({
            "split": "family_disjoint",
            **run_one(
                df, family_masks["fit"], family_masks["holdout"],
                seed=seed, train_n=args.train_n, eval_n=args.eval_n,
                n_features=args.n_features,
            ),
        })
    result = {
        "experiment_id": "R030",
        "tier": "Tier-1 deterministic sampled classifier gate over full-population census/split construction",
        "population": population,
        "model_config": {
            "text": "Unicode-preserving normalized business_name only",
            "vectorizer": "HashingVectorizer char_wb 3-4",
            "n_features": args.n_features,
            "classifier": "SGDClassifier log_loss average",
            "alpha": 1e-5,
            "train_sample_n": args.train_n,
            "eval_sample_n": args.eval_n,
            "seeds": list(args.seeds),
        },
        "runs": runs,
        "total_seconds": time.time() - started,
        "max_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    }
    if args.red_team:
        result["red_team"] = run_red_team(
            df, family_masks["fit"], family_masks["holdout"],
            seed=args.seeds[0], train_n=args.train_n, eval_n=args.eval_n,
            n_features=args.n_features,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source1", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--train-n", type=int, default=200_000)
    parser.add_argument("--eval-n", type=int, default=80_000)
    parser.add_argument("--n-features", type=int, default=2**17)
    parser.add_argument("--seeds", type=int, nargs="+", default=[517, 2026])
    parser.add_argument("--red-team", action="store_true")
    return parser.parse_args()


def main():
    result = run(parse_args())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
