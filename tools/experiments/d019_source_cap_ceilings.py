#!/usr/bin/env python3
"""Audit optimistic macro-F0.5 ceilings for independent S2/S3 hard output caps."""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path


def row_score(truth_size: int, true_positives: int) -> float:
    if truth_size == 0:
        return 1.0
    return (
        1.25 * true_positives / (0.25 * truth_size + true_positives)
        if true_positives
        else 0.0
    )


def summarize(hist: Counter[tuple[int, int]], max_source_cap: int = 6) -> dict:
    n = sum(hist.values())
    if not n:
        raise ValueError("empty histogram")

    global_caps = {}
    for total_cap in range(1, 2 * max_source_cap + 1):
        total = 0.0
        for (s2_count, s3_count), count in hist.items():
            truth_size = s2_count + s3_count
            total += count * row_score(truth_size, min(truth_size, total_cap))
        global_caps[str(total_cap)] = total / n

    surface = {}
    for cap2 in range(max_source_cap + 1):
        for cap3 in range(max_source_cap + 1):
            if cap2 == 0 and cap3 == 0:
                continue
            total = 0.0
            truncated = 0
            for (s2_count, s3_count), count in hist.items():
                truth_size = s2_count + s3_count
                tp = min(s2_count, cap2) + min(s3_count, cap3)
                total += count * row_score(truth_size, tp)
                if s2_count > cap2 or s3_count > cap3:
                    truncated += count
            score = total / n
            same_budget_global = global_caps[str(cap2 + cap3)]
            if score > same_budget_global + 1e-12:
                raise AssertionError(
                    "source-specific cap exceeded same-budget global cap ceiling"
                )
            surface[f"{cap2},{cap3}"] = {
                "score": score,
                "truncated_share": truncated / n,
            }

    comparisons = {}
    for budget in range(1, 2 * max_source_cap + 1):
        options = []
        for key, result in surface.items():
            cap2, cap3 = map(int, key.split(","))
            if cap2 + cap3 == budget:
                options.append((cap2, cap3, result))
        if not options:
            continue
        best = max(
            options,
            key=lambda item: (
                item[2]["score"],
                -abs(item[0] - item[1]),
            ),
        )
        worst = min(options, key=lambda item: item[2]["score"])
        global_score = global_caps[str(budget)]
        comparisons[str(budget)] = {
            "global_cap_score": global_score,
            "best_source_caps": {
                "s2": best[0],
                "s3": best[1],
                **best[2],
            },
            "best_gap_vs_global": best[2]["score"] - global_score,
            "worst_source_caps": {
                "s2": worst[0],
                "s3": worst[1],
                **worst[2],
            },
        }

    return {
        "anchors": n,
        "global_caps": global_caps,
        "source_cap_surface": surface,
        "equal_budget_comparison": comparisons,
    }


def audit(source1: Path, truth: Path, max_source_cap: int = 6) -> dict:
    started = time.time()
    countries: dict[str, str] = {}
    with source1.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            anchor = row["entity_id"]
            if anchor in countries:
                raise ValueError(f"duplicate Source-1 ID: {anchor}")
            countries[anchor] = row["country"]

    overall: Counter[tuple[int, int]] = Counter()
    by_country: defaultdict[str, Counter[tuple[int, int]]] = defaultdict(Counter)
    seen: set[str] = set()
    with truth.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            anchor = row["source1_entity_id"]
            if anchor in seen:
                raise ValueError(f"duplicate truth anchor: {anchor}")
            seen.add(anchor)
            s2_count = 0
            s3_count = 0
            raw = row["matched_entity_ids"].strip()
            if raw:
                for target in raw.split(","):
                    if target.startswith("S2-"):
                        s2_count += 1
                    elif target.startswith("S3-"):
                        s3_count += 1
                    else:
                        raise ValueError(f"unknown target source prefix: {target}")
            country = countries.get(anchor)
            if country is None:
                raise ValueError(f"truth anchor missing Source-1 row: {anchor}")
            overall[(s2_count, s3_count)] += 1
            by_country[country][(s2_count, s3_count)] += 1

    if len(seen) != len(countries):
        raise ValueError("Source-1/truth anchor-set mismatch")

    return {
        "protocol": (
            "Complete train Source-1 + ground truth; truth prefixes only; "
            "no sampling or model probabilities"
        ),
        "joint_source_cardinality_histogram": {
            f"{s2},{s3}": count
            for (s2, s3), count in sorted(overall.items())
        },
        "all": summarize(overall, max_source_cap),
        "countries": {
            country: summarize(hist, max_source_cap)
            for country, hist in sorted(by_country.items())
        },
        "elapsed_seconds": time.time() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source1", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-source-cap", type=int, default=6)
    args = parser.parse_args()
    result = audit(args.source1, args.truth, args.max_source_cap)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
