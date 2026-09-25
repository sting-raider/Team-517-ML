"""R009a: Source-1-only cardinality-prior feasibility audit.

Uses only supplied Source-1 records plus training ground truth. It never uses record IDs
as predictors; IDs are used solely for deterministic fold assignment.
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
from catboost import CatBoostClassifier, CatBoostRegressor


FEATURE_COLUMNS = [
    "name_raw_len", "addr_raw_len", "name_norm_len", "addr_norm_len",
    "name_tokens", "addr_tokens", "name_digit_chars", "addr_digit_chars",
    "name_numeric_tokens", "addr_numeric_tokens", "name_nonascii", "addr_nonascii",
    "name_punct", "addr_punct", "name_spaces", "addr_spaces",
    "name_norm_retention", "addr_norm_retention", "name_missing", "addr_missing",
    "name_freq", "addr_freq", "log_name_freq", "log_addr_freq",
]


def fold_bucket(entity_id: str) -> int:
    return int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100


def fold_name(entity_id: str) -> str:
    bucket = fold_bucket(entity_id)
    return "fit" if bucket < 60 else "early" if bucket < 75 else "calibrate" if bucket < 90 else "holdout"


def normalize(text: str) -> str:
    # Analysis-runtime approximation to DuckDB lower(strip_accents(...)) followed
    # by non-letter/number run collapse. A raw-only robustness model is also run.
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    chars = []
    pending_space = False
    for ch in text:
        if unicodedata.combining(ch):
            continue
        if ch.isalnum():
            if pending_space and chars:
                chars.append(" ")
            chars.append(ch)
            pending_space = False
        else:
            pending_space = True
    return "".join(chars).strip()


def truth_cardinality(value) -> int:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0
    value = str(value).strip()
    return 0 if not value else sum(bool(x.strip()) for x in value.split(","))


def _group_bounds(sorted_scores: np.ndarray):
    if not len(sorted_scores):
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)
    starts = np.r_[0, np.flatnonzero(sorted_scores[1:] != sorted_scores[:-1]) + 1]
    ends = np.r_[starts[1:], len(sorted_scores)]
    return starts, ends


def _auc(y: np.ndarray, score: np.ndarray) -> float:
    y = np.asarray(y, dtype=np.uint8)
    score = np.asarray(score, dtype=np.float64)
    p = int(y.sum())
    n = len(y) - p
    if p == 0 or n == 0:
        return float("nan")
    order = np.argsort(score, kind="mergesort")
    ys, ss = y[order], score[order]
    starts, ends = _group_bounds(ss)
    gp = np.add.reduceat(ys.astype(np.int64), starts)
    sizes = ends - starts
    gn = sizes - gp
    neg_before = np.cumsum(gn) - gn
    wins = np.sum(gp * neg_before + 0.5 * gp * gn)
    return float(wins / (p * n))


def _average_precision(y: np.ndarray, score: np.ndarray) -> float:
    y = np.asarray(y, dtype=np.uint8)
    score = np.asarray(score, dtype=np.float64)
    positives = int(y.sum())
    if positives == 0:
        return float("nan")
    order = np.argsort(-score, kind="mergesort")
    ys, ss = y[order], score[order]
    starts, ends = _group_bounds(ss)
    gp = np.add.reduceat(ys.astype(np.int64), starts)
    sizes = ends - starts
    tp = np.cumsum(gp)
    fp = np.cumsum(sizes - gp)
    recall = tp / positives
    prev = np.r_[0.0, recall[:-1]]
    precision = tp / (tp + fp)
    return float(np.sum((recall - prev) * precision))


def binary_metrics(y: np.ndarray, score: np.ndarray) -> dict:
    y = np.asarray(y, dtype=np.uint8)
    score = np.asarray(score, dtype=np.float64)
    eps = 1e-12
    clipped = np.clip(score, eps, 1 - eps)
    prevalence = float(y.mean())
    constant = np.full(len(y), prevalence, dtype=np.float64)
    return {
        "n": int(len(y)),
        "prevalence": prevalence,
        "auroc": float(_auc(y, score)),
        "auprc": float(_average_precision(y, score)),
        "brier": float(np.mean((score - y) ** 2)),
        "logloss": float(-np.mean(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))),
        "constant_prior_brier": float(np.mean((constant - y) ** 2)),
        "constant_prior_logloss": float(-np.mean(y * np.log(constant) + (1 - y) * np.log(1 - constant))),
    }


def targeting_metrics(y: np.ndarray, score: np.ndarray, fractions=(.01, .025, .05, .1, .2, .3, .4)) -> dict:
    order = np.argsort(-score, kind="mergesort")
    positives = int(y.sum())
    prevalence = positives / len(y)
    out = {}
    for frac in fractions:
        k = max(1, int(round(frac * len(y))))
        tp = int(y[order[:k]].sum())
        precision = tp / k
        out[str(frac)] = {
            "selected": k,
            "precision": precision,
            "recall": tp / positives if positives else None,
            "lift": precision / prevalence if prevalence else None,
            "random_expected_recall": frac,
        }
    return out


def _average_rank(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x)
    order = np.argsort(x, kind="mergesort")
    sx = x[order]
    starts, ends = _group_bounds(sx)
    sizes = ends - starts
    group_ranks = (starts + 1 + ends) / 2.0
    ranks = np.empty(len(x), dtype=np.float64)
    ranks[order] = np.repeat(group_ranks, sizes)
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx, ry = _average_rank(np.asarray(x)), _average_rank(np.asarray(y))
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def build_features(source1: pd.DataFrame) -> pd.DataFrame:
    raw_name = source1["business_name"].fillna("").astype(str)
    raw_addr = source1["business_address"].fillna("").astype(str)
    name = raw_name.map(normalize)
    addr = raw_addr.map(normalize)
    name_vc, addr_vc = name.value_counts(), addr.value_counts()

    f = pd.DataFrame(index=source1.index)
    f["name_raw_len"] = raw_name.str.len()
    f["addr_raw_len"] = raw_addr.str.len()
    f["name_norm_len"] = name.str.len()
    f["addr_norm_len"] = addr.str.len()
    f["name_tokens"] = np.where(name.ne(""), name.str.count(" ") + 1, 0)
    f["addr_tokens"] = np.where(addr.ne(""), addr.str.count(" ") + 1, 0)
    f["name_digit_chars"] = raw_name.str.count(r"\d")
    f["addr_digit_chars"] = raw_addr.str.count(r"\d")
    f["name_numeric_tokens"] = name.str.count(r"(?<!\S)\d+(?!\S)")
    f["addr_numeric_tokens"] = addr.str.count(r"(?<!\S)\d+(?!\S)")
    f["name_nonascii"] = raw_name.str.count(r"[^\x00-\x7F]")
    f["addr_nonascii"] = raw_addr.str.count(r"[^\x00-\x7F]")
    f["name_punct"] = raw_name.str.count(r"[^\w\s]")
    f["addr_punct"] = raw_addr.str.count(r"[^\w\s]")
    f["name_spaces"] = raw_name.str.count(r"\s")
    f["addr_spaces"] = raw_addr.str.count(r"\s")
    f["name_norm_retention"] = f["name_norm_len"] / np.maximum(f["name_raw_len"], 1)
    f["addr_norm_retention"] = f["addr_norm_len"] / np.maximum(f["addr_raw_len"], 1)
    f["name_missing"] = name.eq("")
    f["addr_missing"] = addr.eq("")
    f["name_freq"] = name.map(name_vc)
    f["addr_freq"] = addr.map(addr_vc)
    f["log_name_freq"] = np.log1p(f["name_freq"])
    f["log_addr_freq"] = np.log1p(f["addr_freq"])
    return f[FEATURE_COLUMNS].astype(np.float32)


def build_raw_features(source1: pd.DataFrame) -> pd.DataFrame:
    raw_name = source1["business_name"].fillna("").astype(str)
    raw_addr = source1["business_address"].fillna("").astype(str)
    raw_name_vc, raw_addr_vc = raw_name.value_counts(), raw_addr.value_counts()
    r = pd.DataFrame(index=source1.index)
    r["name_raw_len"] = raw_name.str.len()
    r["addr_raw_len"] = raw_addr.str.len()
    r["name_digit_chars"] = raw_name.str.count(r"\d")
    r["addr_digit_chars"] = raw_addr.str.count(r"\d")
    r["name_nonascii"] = raw_name.str.count(r"[^\x00-\x7F]")
    r["addr_nonascii"] = raw_addr.str.count(r"[^\x00-\x7F]")
    r["name_punct"] = raw_name.str.count(r"[^\w\s]")
    r["addr_punct"] = raw_addr.str.count(r"[^\w\s]")
    r["name_spaces"] = raw_name.str.count(r"\s")
    r["addr_spaces"] = raw_addr.str.count(r"\s")
    r["name_missing"] = raw_name.eq("")
    r["addr_missing"] = raw_addr.eq("")
    r["raw_name_freq"] = raw_name.map(raw_name_vc)
    r["raw_addr_freq"] = raw_addr.map(raw_addr_vc)
    r["log_raw_name_freq"] = np.log1p(r["raw_name_freq"])
    r["log_raw_addr_freq"] = np.log1p(r["raw_addr_freq"])
    return r.astype(np.float32)


def run(source1_path: Path, truth_path: Path, out: Path, strong_check: bool = False, raw_check: bool = False) -> dict:
    started = time.time()
    source1 = pd.read_csv(source1_path, sep="\t", dtype=str, keep_default_na=False)
    truth = pd.read_csv(truth_path, sep="\t", dtype=str, keep_default_na=False)
    if source1["entity_id"].duplicated().any() or truth["source1_entity_id"].duplicated().any():
        raise ValueError("Duplicate anchor IDs detected")
    card = truth.set_index("source1_entity_id")["matched_entity_ids"].map(truth_cardinality)
    source1["cardinality"] = source1["entity_id"].map(card)
    if source1["cardinality"].isna().any() or len(source1) != len(truth):
        raise ValueError("Source-1 / truth anchor mismatch")

    features = build_features(source1)
    x = features.to_numpy(np.float32, copy=False)
    y_card = source1["cardinality"].to_numpy(np.float32)
    y = (y_card >= 5).astype(np.uint8)
    buckets = np.fromiter((fold_bucket(eid) for eid in source1["entity_id"]), dtype=np.uint8, count=len(source1))
    masks = {
        "fit": buckets < 60,
        "early": (buckets >= 60) & (buckets < 75),
        "calibrate": (buckets >= 75) & (buckets < 90),
        "holdout": buckets >= 90,
    }

    model = CatBoostClassifier(iterations=100, depth=7, learning_rate=.08, loss_function="Logloss",
                               random_seed=517, thread_count=8, verbose=False,
                               allow_writing_files=False, l2_leaf_reg=5)
    model.fit(x[masks["fit"]], y[masks["fit"]])
    prob = model.predict_proba(x)[:, 1]
    classification = {name: binary_metrics(y[mask], prob[mask]) for name, mask in masks.items()}
    countries = source1["country"].to_numpy()
    for country in sorted(source1["country"].unique()):
        mask = masks["holdout"] & (countries == country)
        classification["holdout_" + country] = binary_metrics(y[mask], prob[mask])

    reg = CatBoostRegressor(iterations=100, depth=7, learning_rate=.08, loss_function="RMSE",
                            random_seed=517, thread_count=8, verbose=False,
                            allow_writing_files=False, l2_leaf_reg=5)
    reg.fit(x[masks["fit"]], y_card[masks["fit"]])
    pred_card = reg.predict(x)
    fit_mean = float(y_card[masks["fit"]].mean())
    fit_median = float(np.median(y_card[masks["fit"]]))

    def regress(mask):
        yy, pp = y_card[mask], pred_card[mask]
        return {
            "n": int(mask.sum()),
            "mae": float(np.mean(np.abs(yy - pp))),
            "rmse": float(np.sqrt(np.mean((yy - pp) ** 2))),
            "spearman": spearman(yy, pp),
            "baseline_mean_rmse": float(np.sqrt(np.mean((yy - fit_mean) ** 2))),
            "baseline_median_mae": float(np.mean(np.abs(yy - fit_median))),
        }

    regression = {name: regress(mask) for name, mask in masks.items()}
    for country in sorted(source1["country"].unique()):
        regression["holdout_" + country] = regress(masks["holdout"] & (countries == country))

    result = {
        "experiment_id": "R009a",
        "rows": int(len(source1)),
        "high_cardinality_definition": "truth cardinality >= 5",
        "high_cardinality_count": int(y.sum()),
        "high_cardinality_prevalence": float(y.mean()),
        "fold_counts": {name: int(mask.sum()) for name, mask in masks.items()},
        "feature_names": FEATURE_COLUMNS,
        "primary_classifier": {
            "config": {"iterations": 100, "depth": 7, "learning_rate": .08, "seed": 517},
            "metrics": classification,
            "holdout_targeting": targeting_metrics(y[masks["holdout"]], prob[masks["holdout"]]),
            "feature_importance": dict(sorted(zip(FEATURE_COLUMNS, map(float, model.feature_importances_)),
                                              key=lambda kv: -kv[1])),
        },
        "regression": {
            "config": {"iterations": 100, "depth": 7, "learning_rate": .08, "seed": 517},
            "metrics": regression,
        },
        "normalization_note": "NFKD accent folding approximation; raw-only check removes dependence on this choice.",
        "elapsed_seconds": time.time() - started,
    }

    if raw_check:
        raw_features = build_raw_features(source1)
        xr = raw_features.to_numpy(np.float32, copy=False)
        raw_model = CatBoostClassifier(iterations=100, depth=7, learning_rate=.08, loss_function="Logloss",
                                       random_seed=517, thread_count=8, verbose=False,
                                       allow_writing_files=False, l2_leaf_reg=5)
        raw_model.fit(xr[masks["fit"]], y[masks["fit"]])
        raw_prob = raw_model.predict_proba(xr[masks["holdout"]])[:, 1]
        result["raw_only_robustness"] = binary_metrics(y[masks["holdout"]], raw_prob)

    if strong_check:
        strong = CatBoostClassifier(iterations=200, depth=8, learning_rate=.08, loss_function="Logloss",
                                    random_seed=517, thread_count=8, verbose=False,
                                    allow_writing_files=False, l2_leaf_reg=5)
        strong.fit(x[masks["fit"]], y[masks["fit"]])
        sp = strong.predict_proba(x[masks["holdout"]])[:, 1]
        result["stronger_classifier_check"] = {
            "config": {"iterations": 200, "depth": 8, "learning_rate": .08, "seed": 517},
            "holdout": binary_metrics(y[masks["holdout"]], sp),
            "holdout_targeting": targeting_metrics(y[masks["holdout"]], sp),
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source1", type=Path, required=True)
    p.add_argument("--truth", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--strong-check", action="store_true")
    p.add_argument("--raw-check", action="store_true")
    args = p.parse_args()
    result = run(args.source1, args.truth, args.out, args.strong_check, args.raw_check)
    print(json.dumps({
        "experiment_id": result["experiment_id"],
        "rows": result["rows"],
        "holdout": result["primary_classifier"]["metrics"]["holdout"],
        "regression_holdout": result["regression"]["metrics"]["holdout"],
        "elapsed_seconds": result["elapsed_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
