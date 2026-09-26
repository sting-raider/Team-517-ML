#!/usr/bin/env python3
"""Audit INT003 fit-population composition and anchor-balanced weighting premise.

This helper requires only train_source1.tsv and train_ground_truth.tsv. It never
loads S2/S3 records and never uses record IDs as predictive features; IDs are used
only to reproduce the repository's deterministic sample/fold selection.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

TOP_N = 200_000


def fold517(entity_id: str) -> str:
    bucket = int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100
    if bucket < 60:
        return "fit"
    if bucket < 75:
        return "early"
    if bucket < 90:
        return "calibrate"
    return "holdout"


def in_int003_fit(sample_position: int, entity_id: str) -> bool:
    return fold517(entity_id) == "fit" and (
        sample_position <= 30_000 or 50_000 < sample_position <= 200_000
    )


def cardinality_stats(counter: Counter[int]) -> dict:
    n = sum(counter.values())
    if n <= 0:
        raise ValueError("cardinality counter is empty")
    return {
        "anchors": n,
        "mean_truth_cardinality": sum(k * v for k, v in counter.items()) / n,
        "empty_truth_rate": counter.get(0, 0) / n,
        "one_match_rate": counter.get(1, 0) / n,
        "two_plus_rate": sum(v for k, v in counter.items() if k >= 2) / n,
        "five_plus_rate": sum(v for k, v in counter.items() if k >= 5) / n,
        "cardinality_counts": {str(k): counter[k] for k in sorted(counter)},
    }


def anchor_mass_from_inverse_count_weights(candidate_counts: list[int]) -> list[float]:
    """Return total normalized row-weight mass per nonempty anchor."""
    if not candidate_counts or any(n <= 0 for n in candidate_counts):
        raise ValueError("candidate counts must be positive")
    row_count = sum(candidate_counts)
    raw_weight_sum = float(len(candidate_counts))
    mean_raw_weight = raw_weight_sum / row_count
    return [(n * (1.0 / n)) / mean_raw_weight for n in candidate_counts]


def _truth_cardinalities(path: Path) -> tuple[dict[str, int], Counter[int]]:
    values: dict[str, int] = {}
    overall: Counter[int] = Counter()
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = csv.reader(stream, delimiter="\t")
        header = next(rows)
        if header != ["source1_entity_id", "matched_entity_ids"]:
            raise ValueError(f"unexpected truth header: {header}")
        for line_number, row in enumerate(rows, 2):
            if len(row) != 2:
                raise ValueError(f"truth row {line_number} has {len(row)} fields")
            entity_id, matches = row
            if entity_id in values:
                raise ValueError(f"duplicate truth entity: {entity_id}")
            cardinality = 0 if not matches else matches.count(",") + 1
            values[entity_id] = cardinality
            overall[cardinality] += 1
    return values, overall


def audit(source1: Path, truth: Path, committed_training_pairs: int = 16_043_969) -> dict:
    started = time.time()
    truth_cardinality, overall = _truth_cardinalities(truth)
    countries: defaultdict[str, Counter[int]] = defaultdict(Counter)
    smallest_md5: list[tuple[int, str, str, int]] = []
    source1_count = 0

    with source1.open("r", encoding="utf-8", newline="") as stream:
        rows = csv.reader(stream, delimiter="\t")
        header = next(rows)
        if header != ["entity_id", "business_name", "business_address", "country"]:
            raise ValueError(f"unexpected Source-1 header: {header}")
        for line_number, row in enumerate(rows, 2):
            if len(row) != 4:
                raise ValueError(f"Source-1 row {line_number} has {len(row)} fields")
            entity_id, _, _, country = row
            try:
                cardinality = truth_cardinality[entity_id]
            except KeyError as exc:
                raise ValueError(f"missing truth for {entity_id}") from exc
            countries[country][cardinality] += 1
            digest = int.from_bytes(hashlib.md5(("sample517:" + entity_id).encode()).digest(), "big")
            item = (-digest, entity_id, country, cardinality)
            if len(smallest_md5) < TOP_N:
                heapq.heappush(smallest_md5, item)
            elif digest < -smallest_md5[0][0]:
                heapq.heapreplace(smallest_md5, item)
            source1_count += 1

    if source1_count != len(truth_cardinality):
        raise ValueError(
            f"Source-1/truth universe mismatch: {source1_count} vs {len(truth_cardinality)}"
        )

    ordered = sorted(
        [(-negative_digest, entity_id, country, cardinality)
         for negative_digest, entity_id, country, cardinality in smallest_md5],
        key=lambda row: (row[0], row[1]),
    )
    fit: Counter[int] = Counter()
    fit_country: defaultdict[str, Counter[int]] = defaultdict(Counter)
    first30_folds: Counter[str] = Counter()
    post50_folds: Counter[str] = Counter()

    for position, (_, entity_id, country, cardinality) in enumerate(ordered, 1):
        selected_fold = fold517(entity_id)
        if position <= 30_000:
            first30_folds[selected_fold] += 1
        elif position > 50_000:
            post50_folds[selected_fold] += 1
        if in_int003_fit(position, entity_id):
            fit[cardinality] += 1
            fit_country[country][cardinality] += 1

    population_stats = cardinality_stats(overall)
    fit_stats = cardinality_stats(fit)

    def bernoulli_smd(metric: str) -> float:
        p = population_stats[metric]
        q = fit_stats[metric]
        return (q - p) / math.sqrt(max(1e-15, p * (1 - p)))

    fit_anchors = fit_stats["anchors"]
    return {
        "protocol": {
            "source1_rows": source1_count,
            "selection": (
                "fold517=='fit' and (sample_position<=30000 or "
                "50000<sample_position<=200000) under md5('sample517:'||entity_id) ordering"
            ),
            "committed_int003_training_pairs": committed_training_pairs,
        },
        "population": population_stats,
        "population_by_country": {
            country: cardinality_stats(counter) for country, counter in sorted(countries.items())
        },
        "int003_fit": fit_stats,
        "int003_fit_by_country": {
            country: cardinality_stats(counter) for country, counter in sorted(fit_country.items())
        },
        "selection_checks": {
            "top200k_rows": len(ordered),
            "fit_anchors": fit_anchors,
            "fit_country_counts": {
                country: sum(counter.values()) for country, counter in sorted(fit_country.items())
            },
            "first30k_fold_counts": dict(sorted(first30_folds.items())),
            "positions_50001_200000_fold_counts": dict(sorted(post50_folds.items())),
        },
        "fit_vs_population": {
            "mean_cardinality_delta": (
                fit_stats["mean_truth_cardinality"] - population_stats["mean_truth_cardinality"]
            ),
            "empty_truth_rate_delta_pp": 100 * (
                fit_stats["empty_truth_rate"] - population_stats["empty_truth_rate"]
            ),
            "five_plus_rate_delta_pp": 100 * (
                fit_stats["five_plus_rate"] - population_stats["five_plus_rate"]
            ),
            "empty_truth_smd": bernoulli_smd("empty_truth_rate"),
            "five_plus_smd": bernoulli_smd("five_plus_rate"),
        },
        "weight_invariant": {
            "equal_total_mass_for_every_nonempty_candidate_group": True,
            "proof": (
                "For anchor g with n_g rows, sum_j (1/n_g)/mean_raw = "
                "1/mean_raw, independent of n_g."
            ),
            "mean_fit_candidate_rows_from_committed_int003": committed_training_pairs / fit_anchors,
            "scope_limit": (
                "Private fit candidate arrays are not part of this audit, so zero-candidate-anchor "
                "prevalence and weighted positive-candidate fractions are not remeasured."
            ),
        },
        "elapsed_seconds": time.time() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source1", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--training-pairs", type=int, default=16_043_969)
    args = parser.parse_args()
    result = audit(args.source1, args.truth, args.training_pairs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
