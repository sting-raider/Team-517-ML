#!/usr/bin/env python3
"""Full-population truth-cardinality cost audit for the official macro F0.5 metric."""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

BETA2 = 0.25


def row_score_from_counts(truth_size: int, true_positives: int, false_positives: int) -> float:
    """Exact src/ber/metrics.py row_score expressed only through set cardinalities."""
    predicted_size = true_positives + false_positives
    if truth_size == 0:
        return float(predicted_size == 0)
    if not (0 <= true_positives <= truth_size):
        raise ValueError("true_posititives must be between 0 and truth_size")
    if false_positives < 0:
        raise ValueError("false_positives must be non-negative")
    return 1.25 * true_positives / (BETA2 * truth_size + predicted_size)


def percentile_from_hist(hist: Counter[int], q: float) -> int | None:
    if not hist:
        return None
    if not 0 <= q <= 1:
        raise ValueError("q must be in [0,1]")
    n = sum(hist.values())
    rank = max(1, math.ceil(q * n))
    seen = 0
    for cardinality in sorted(hist):
        seen += hist[cardinality]
        if seen >= rank:
            return cardinality
    raise AssertionError("unreachable")


def summarize_hist(hist: Counter[int]) -> dict:
    n = sum(hist.values())
    if n == 0:
        raise ValueError("empty histogram")
    singleton_count = hist.get(0, 0)
    non_singletons = n - singleton_count

    hard_cap = {}
    for cap in range(1, 11):
        total = 0.0
        for truth_size, count in hist.items():
            tp = min(truth_size, cap)
            total += count * row_score_from_counts(truth_size, tp, 0)
        hard_cap[str(cap)] = total / n

    add_fp_loss = 0.0
    drop_true_loss = 0.0
    fp_costlier_count = 0
    per_cardinality = {}
    for truth_size, count in hist.items():
        fp_score = row_score_from_counts(truth_size, truth_size, 1) if truth_size else 0.0
        fp_loss = 1.0 - fp_score
        add_fp_loss += count * fp_loss
        if truth_size:
            fn_score = row_score_from_counts(truth_size, truth_size - 1, 0)
            fn_loss = 1.0 - fn_score
            drop_true_loss += count * fn_loss
            if fp_loss > fn_loss:
                fp_costlier_count += count
            per_cardinality[str(truth_size)] = {
                "one_fp_loss": fp_loss,
                "one_fn_loss": fn_loss,
                "fp_over_fn_loss_ratio": fp_loss / fn_loss,
            }
        else:
            per_cardinality["0"] = {
                "one_fp_loss": 1.0,
                "one_fn_loss": None,
                "fp_over_fn_loss_ratio": None,
            }

    return {
        "anchors": n,
        "singleton_count": singleton_count,
        "singleton_rate": singleton_count / n,
        "mean_truth_cardinality": sum(k * v for k, v in hist.items()) / n,
        "cardinality_quantiles": {
            "p50": percentile_from_hist(hist, 0.50),
            "p90": percentile_from_hist(hist, 0.90),
            "p95": percentile_from_hist(hist, 0.95),
            "p99": percentile_from_hist(hist, 0.99),
            "max": max(hist),
        },
        "hard_cap_perfect_ranking_macro_f0_5": hard_cap,
        "mean_loss_add_one_fp_from_perfect": add_fp_loss / n,
        "mean_loss_drop_one_true_match_non_singletons": drop_true_loss / non_singletons,
        "non_singleton_anchors": non_singletons,
        "fp_costlier_than_fn_count": fp_costlier_count,
        "fp_costlier_than_fn_share_all": fp_costlier_count / n,
        "fp_costlier_than_fn_share_non_singletons": fp_costlier_count / non_singletons,
        "one_error_cost_by_cardinality": per_cardinality,
    }


def audit(source1: Path, truth: Path) -> dict:
    started = time.time()
    countries: dict[str, str] = {}
    duplicate_s1 = 0
    with source1.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"entity_id", "country"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Source-1 missing columns: {sorted(required - set(reader.fieldnames or []))}")
        for row in reader:
            anchor = row["entity_id"]
            if anchor in countries:
                duplicate_s1 += 1
            countries[anchor] = row["country"]
    if duplicate_s1:
        raise ValueError(f"duplicate Source-1 IDs: {duplicate_s1}")

    overall: Counter[int] = Counter()
    by_country: defaultdict[str, Counter[int]] = defaultdict(Counter)
    seen_truth: set[str] = set()
    duplicate_truth = 0
    missing_country = 0
    with truth.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"source1_entity_id", "matched_entity_ids"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"truth missing columns: {sorted(required - set(reader.fieldnames or []))}")
        for row in reader:
            anchor = row["source1_entity_id"]
            if anchor in seen_truth:
                duplicate_truth += 1
            seen_truth.add(anchor)
            raw = row["matched_entity_ids"].strip()
            cardinality = 0 if not raw else raw.count(",") + 1
            overall[cardinality] += 1
            country = countries.get(anchor)
            if country is None:
                missing_country += 1
            else:
                by_country[country][cardinality] += 1
    if duplicate_truth:
        raise ValueError(f"duplicate truth anchor IDs: {duplicate_truth}")
    if missing_country:
        raise ValueError(f"truth anchors missing Source-1 country: {missing_country}")
    if len(seen_truth) != len(countries):
        missing_truth = len(set(countries) - seen_truth)
        raise ValueError(
            f"Source-1/truth anchor mismatch: source1={len(countries)} "
            f"truth={len(seen_truth)} missing_truth={missing_truth}"
        )

    return {
        "protocol": (
            "Complete train Source-1 + ground truth; exact truth-set cardinality; "
            "no sampling; no candidate/model probabilities"
        ),
        "source1_rows": len(countries),
        "truth_rows": len(seen_truth),
        "cardinality_histogram": {str(k): v for k, v in sorted(overall.items())},
        "all": summarize_hist(overall),
        "countries": {
            country: summarize_hist(hist) for country, hist in sorted(by_country.items())
        },
        "elapsed_seconds": time.time() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source1", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.source1, args.truth)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
