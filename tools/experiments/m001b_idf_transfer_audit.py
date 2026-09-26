"""M001b: train/test transfer audit for M001a split-local token-IDF profiles."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from tools.experiments.m001a_idf_pair_feasibility import census, idf_weight, probe


def weighted_quantiles(values, weights, points=(.5, .9, .95, .99)) -> dict:
    values = np.asarray(values, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    if len(values) == 0:
        return {}
    if len(values) != len(weights) or np.any(weights < 0):
        raise ValueError("values/weights mismatch or negative weight")
    order = np.argsort(values, kind="mergesort")
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    total = cumulative[-1]
    if total <= 0:
        raise ValueError("positive total weight required")
    return {
        str(q): float(values[min(np.searchsorted(cumulative, q * total, side="left"), len(values) - 1)])
        for q in points
    }


def average_ranks(values) -> np.ndarray:
    """Average ranks for ties, dependency-light scipy.stats.rankdata equivalent."""
    x = np.asarray(values, dtype=np.float64)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=np.float64)
    start = 0
    while start < len(x):
        end = start + 1
        while end < len(x) and x[order[end]] == x[order[start]]:
            end += 1
        # zero-based average rank is sufficient for correlation.
        rank = (start + end - 1) / 2.0
        ranks[order[start:end]] = rank
        start = end
    return ranks


def spearman(values_a, values_b) -> float:
    if len(values_a) != len(values_b) or len(values_a) < 2:
        return float("nan")
    ra, rb = average_ranks(values_a), average_ranks(values_b)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def compare_profiles(train: dict, test: dict, field: str) -> dict:
    train_df, test_df = train[field], test[field]
    train_n, test_n = train["rows"], test["rows"]
    shared = sorted(set(train_df) & set(test_df))
    novel = set(test_df) - set(train_df)
    test_postings = sum(test_df.values())
    novel_postings = sum(test_df[token] for token in novel)

    train_rates = np.asarray([train_df[t] / train_n for t in shared], dtype=np.float64)
    test_rates = np.asarray([test_df[t] / test_n for t in shared], dtype=np.float64)
    train_idf = np.asarray([idf_weight(train_n, train_df[t]) for t in shared])
    test_idf = np.asarray([idf_weight(test_n, test_df[t]) for t in shared])
    drift = np.abs(train_idf - test_idf)
    posting_weights = np.asarray([test_df[t] for t in shared], dtype=np.float64)
    shared_mass = posting_weights.sum()

    return {
        "train_vocab": len(train_df),
        "test_vocab": len(test_df),
        "shared_vocab": len(shared),
        "test_vocab_unseen_rate": len(novel) / len(test_df) if test_df else 0.0,
        "test_posting_unseen_rate": novel_postings / test_postings if test_postings else 0.0,
        "shared_df_spearman": spearman(train_rates, test_rates),
        "shared_test_posting_weighted_abs_idf_drift_mean": (
            float(np.average(drift, weights=posting_weights)) if len(shared) else None
        ),
        "shared_test_posting_weighted_abs_idf_drift_quantiles": weighted_quantiles(
            drift, posting_weights
        ) if len(shared) else {},
        "shared_test_posting_abs_idf_drift_gt_0_25": (
            float(posting_weights[drift > .25].sum() / shared_mass) if shared_mass else 0.0
        ),
        "shared_test_posting_abs_idf_drift_gt_0_5": (
            float(posting_weights[drift > .5].sum() / shared_mass) if shared_mass else 0.0
        ),
        "shared_test_posting_abs_idf_drift_gt_1": (
            float(posting_weights[drift > 1].sum() / shared_mass) if shared_mass else 0.0
        ),
        "train_posting_weighted_idf_quantiles": local_idf_summary(train, field)[
            "posting_weighted_idf_quantiles"
        ],
        "test_posting_weighted_idf_quantiles": local_idf_summary(test, field)[
            "posting_weighted_idf_quantiles"
        ],
    }


def local_idf_summary(profile: dict, field: str) -> dict:
    df = profile[field]
    n = profile["rows"]
    tokens = list(df)
    values = np.asarray([idf_weight(n, df[t]) for t in tokens], dtype=np.float64)
    weights = np.asarray([df[t] for t in tokens], dtype=np.float64)
    dfs = np.asarray([df[t] for t in tokens], dtype=np.float64)
    return {
        "rows": n,
        "vocab": len(df),
        "postings": int(weights.sum()),
        "posting_weighted_idf_quantiles": weighted_quantiles(
            values, weights, (.1, .25, .5, .75, .9, .95, .99)
        ),
        "vocab_df_quantiles": {
            str(q): float(np.quantile(dfs, q)) for q in (.5, .9, .95, .99)
        },
        "max_df": int(dfs.max()) if len(dfs) else 0,
    }


def audit(train_path: Path, test_path: Path) -> dict:
    train = {country: census(train_path, country) for country in ("US", "India")}
    test = {country: census(test_path, country) for country in ("US", "India", "France")}

    transfer = {
        country: {
            field: compare_profiles(train[country], test[country], field)
            for field in ("name", "address")
        }
        for country in ("US", "India")
    }
    france = {
        "name": local_idf_summary(test["France"], "name"),
        "address": local_idf_summary(test["France"], "address"),
        "deletion_probe": probe(test_path, test["France"])["fields"],
    }
    return {
        "experiment_id": "M001b",
        "status": "PROMOTE-EMPIRICAL-GATE",
        "transfer": transfer,
        "france": france,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-source1", type=Path, required=True)
    parser.add_argument("--test-source1", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.train_source1, args.test_source1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
