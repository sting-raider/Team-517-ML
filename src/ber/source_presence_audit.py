"""D012 full-data Source-1-only source-presence prior audit.

Uses only supplied train_source1.tsv + train_ground_truth.tsv.
Entity IDs are used solely for deterministic fold517 assignment and never as features.
No row-level predictions or model binaries are persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

FEATURE_NAMES = [
    "raw_name_len", "raw_address_len", "norm_name_len", "norm_address_len",
    "name_token_count", "address_token_count", "name_digit_chars", "address_digit_chars",
    "name_numeric_token_count", "address_numeric_token_count",
    "name_nonascii_count", "address_nonascii_count",
    "name_punct_count", "address_punct_count", "name_whitespace_count", "address_whitespace_count",
    "name_norm_retention", "address_norm_retention",
    "norm_name_freq", "norm_address_freq", "norm_name_address_freq",
    "log1p_name_freq", "log1p_address_freq", "log1p_name_address_freq",
]
TARGETS = ("s2_present", "s3_present", "both_source", "s2_only", "s3_only")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_text(s: str) -> str:
    """Mirror D001a's no-DuckDB fallback normalization."""
    s = unicodedata.normalize("NFD", s).lower()
    out = []
    prev_space = True
    for ch in s:
        if unicodedata.category(ch) == "Mn":
            continue
        if ch.isalnum():
            out.append(ch)
            prev_space = False
        elif not prev_space:
            out.append(" ")
            prev_space = True
    if out and out[-1] == " ":
        out.pop()
    return "".join(out)


def fold_bucket(entity_id: str) -> int:
    return int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100


def build_features(s1: pd.DataFrame):
    n = s1["business_name"].map(norm_text)
    a = s1["business_address"].map(norm_text)
    nfreq = n.value_counts(dropna=False)
    afreq = a.value_counts(dropna=False)
    pair_hash = pd.util.hash_pandas_object(pd.DataFrame({"n": n, "a": a}), index=False)
    pfreq = pair_hash.value_counts()

    N = len(s1)
    X = np.empty((N, len(FEATURE_NAMES)), dtype=np.float32)
    rn = s1["business_name"]
    ra = s1["business_address"]
    rnlen = rn.str.len().to_numpy(dtype=np.float32)
    ralen = ra.str.len().to_numpy(dtype=np.float32)
    nlen = n.str.len().to_numpy(dtype=np.float32)
    alen = a.str.len().to_numpy(dtype=np.float32)

    X[:, 0] = rnlen
    X[:, 1] = ralen
    X[:, 2] = nlen
    X[:, 3] = alen
    X[:, 4] = np.where(nlen > 0, n.str.count(" ").to_numpy(dtype=np.float32) + 1, 0)
    X[:, 5] = np.where(alen > 0, a.str.count(" ").to_numpy(dtype=np.float32) + 1, 0)
    X[:, 6] = rn.str.count(r"\d").to_numpy(dtype=np.float32)
    X[:, 7] = ra.str.count(r"\d").to_numpy(dtype=np.float32)
    X[:, 8] = n.str.count(r"(?:^| )\d+(?= |$)").to_numpy(dtype=np.float32)
    X[:, 9] = a.str.count(r"(?:^| )\d+(?= |$)").to_numpy(dtype=np.float32)
    X[:, 10] = rn.str.count(r"[^\x00-\x7F]").to_numpy(dtype=np.float32)
    X[:, 11] = ra.str.count(r"[^\x00-\x7F]").to_numpy(dtype=np.float32)
    X[:, 12] = rn.map(
        lambda s: sum((not ch.isalnum()) and (not ch.isspace()) for ch in s)
    ).to_numpy(dtype=np.float32)
    X[:, 13] = ra.map(
        lambda s: sum((not ch.isalnum()) and (not ch.isspace()) for ch in s)
    ).to_numpy(dtype=np.float32)
    X[:, 14] = rn.str.count(r"\s").to_numpy(dtype=np.float32)
    X[:, 15] = ra.str.count(r"\s").to_numpy(dtype=np.float32)
    X[:, 16] = np.divide(nlen, np.maximum(rnlen, 1), dtype=np.float32)
    X[:, 17] = np.divide(alen, np.maximum(ralen, 1), dtype=np.float32)

    nf = n.map(nfreq).to_numpy(dtype=np.float32)
    af = a.map(afreq).to_numpy(dtype=np.float32)
    pf = pair_hash.map(pfreq).to_numpy(dtype=np.float32)
    X[:, 18] = nf
    X[:, 19] = af
    X[:, 20] = pf
    X[:, 21] = np.log1p(nf)
    X[:, 22] = np.log1p(af)
    X[:, 23] = np.log1p(pf)

    diagnostics = {
        "name_collision_anchor_rate": float(np.mean(nf > 1)),
        "address_collision_anchor_rate": float(np.mean(af > 1)),
        "name_address_collision_anchor_rate": float(np.mean(pf > 1)),
        "unique_norm_names": int(len(nfreq)),
        "unique_norm_addresses": int(len(afreq)),
    }
    return X, diagnostics


def build_labels(s1: pd.DataFrame, gt: pd.DataFrame):
    if gt["source1_entity_id"].duplicated().any():
        raise ValueError("duplicate ground-truth anchors")
    m = gt["matched_entity_ids"]
    s2 = m.str.contains("S2-", regex=False).to_numpy()
    s3 = m.str.contains("S3-", regex=False).to_numpy()
    bits = s2.astype(np.uint8) | (s3.astype(np.uint8) << 1)
    label_map = pd.Series(bits, index=gt["source1_entity_id"])
    aligned = s1["entity_id"].map(label_map)
    if aligned.isna().any():
        raise ValueError("Source-1 anchors missing ground truth")
    b = aligned.to_numpy(dtype=np.uint8)
    return {
        "s2_present": (b & 1) > 0,
        "s3_present": (b & 2) > 0,
        "both_source": b == 3,
        "s2_only": b == 1,
        "s3_only": b == 2,
    }


def auc_ci_hanley(auc: float, y: np.ndarray):
    n1 = int(y.sum())
    n0 = int(len(y) - n1)
    q1 = auc / (2 - auc)
    q2 = 2 * auc * auc / (1 + auc)
    var = (
        auc * (1 - auc)
        + (n1 - 1) * (q1 - auc * auc)
        + (n0 - 1) * (q2 - auc * auc)
    ) / (n1 * n0)
    se = math.sqrt(max(var, 0))
    return [auc - 1.96 * se, auc + 1.96 * se], se


def metrics(y, p, mask, fit_prevalence):
    yy = y[mask]
    pp = p[mask]
    auc = float(roc_auc_score(yy, pp))
    ci, se = auc_ci_hanley(auc, yy)
    return {
        "n": int(mask.sum()),
        "prevalence": float(yy.mean()),
        "auroc": auc,
        "auroc_ci95_approx": ci,
        "auroc_se_approx": se,
        "auprc": float(average_precision_score(yy, pp)),
        "brier": float(brier_score_loss(yy, pp)),
        "constant_fit_prior_brier": float(np.mean((yy - fit_prevalence) ** 2)),
    }


def run(source1: Path, truth: Path, out: Path, seed=517, trees=100):
    started = time.time()
    s1 = pd.read_csv(source1, sep="\t", dtype=str, keep_default_na=False)
    gt = pd.read_csv(truth, sep="\t", dtype=str, keep_default_na=False)
    if len(s1) != len(gt):
        raise ValueError("Source-1/truth row count mismatch")

    X, feature_diag = build_features(s1)
    labels = build_labels(s1, gt)
    bucket = np.fromiter(
        (fold_bucket(e) for e in s1["entity_id"]), dtype=np.uint8, count=len(s1)
    )
    fold = np.select([bucket < 60, bucket < 75, bucket < 90], [0, 1, 2], default=3).astype(np.uint8)
    country = s1["country"].to_numpy()
    masks = {
        "fit": fold == 0,
        "early": fold == 1,
        "calibrate": fold == 2,
        "holdout": fold == 3,
        "holdout_US": (fold == 3) & (country == "US"),
        "holdout_India": (fold == 3) & (country == "India"),
    }

    result = {
        "experiment_id": "D012",
        "inputs": {
            "source1": str(source1),
            "source1_bytes": source1.stat().st_size,
            "source1_sha256": sha256_file(source1),
            "truth": str(truth),
            "truth_bytes": truth.stat().st_size,
            "truth_sha256": sha256_file(truth),
            "anchors": int(len(s1)),
        },
        "protocol": {
            "split": "sha256('fold517:'+entity_id) first 8 hex %100; 60/15/15/10",
            "features": FEATURE_NAMES,
            "country_feature": False,
            "id_feature": False,
            "model": {
                "type": "CatBoostClassifier",
                "iterations": trees,
                "depth": 7,
                "learning_rate": 0.08,
                "loss_function": "Logloss",
                "random_seed": seed,
                "l2_leaf_reg": 5,
            },
            "normalization": "NFD combining-mark removal + lowercase + unicode alnum runs; same fallback as D001a",
        },
        "fold_counts": {
            k: int(v.sum()) for k, v in masks.items()
            if k in ("fit", "early", "calibrate", "holdout")
        },
        "feature_diagnostics": feature_diag,
        "targets": {},
    }

    fit = masks["fit"]
    for name in TARGETS:
        y = labels[name].astype(np.uint8)
        fit_prev = float(y[fit].mean())
        model = CatBoostClassifier(
            iterations=trees,
            depth=7,
            learning_rate=.08,
            loss_function="Logloss",
            random_seed=seed,
            thread_count=6,
            verbose=False,
            allow_writing_files=False,
            l2_leaf_reg=5,
        )
        t = time.time()
        model.fit(X[fit], y[fit])
        train_seconds = time.time() - t
        t = time.time()
        p = model.predict_proba(X, thread_count=6)[:, 1]
        predict_seconds = time.time() - t
        result["targets"][name] = {
            "population_prevalence": float(y.mean()),
            "fit_prevalence": fit_prev,
            "train_seconds": train_seconds,
            "predict_seconds": predict_seconds,
            "metrics": {
                sl: metrics(y, p, mask, fit_prev)
                for sl, mask in masks.items()
            },
            "feature_importance": dict(
                sorted(
                    zip(FEATURE_NAMES, map(float, model.feature_importances_)),
                    key=lambda kv: -kv[1],
                )
            ),
        }

    result["elapsed_seconds"] = time.time() - started
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source1", type=Path, required=True)
    p.add_argument("--truth", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=517)
    p.add_argument("--trees", type=int, default=100)
    a = p.parse_args()
    run(a.source1, a.truth, a.out, a.seed, a.trees)


if __name__ == "__main__":
    main()
