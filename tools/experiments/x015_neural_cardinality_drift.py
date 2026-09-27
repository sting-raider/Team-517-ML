#!/usr/bin/env python3
"""Aggregate-only cardinality transfer audit for INT003/V5/V6 outputs.

This script reads complete Source-1 + ground-truth TSVs but writes only aggregate
counts. Test labels are neither required nor accepted. V5/V6 output statistics
come from committed aggregate JSON receipts.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path


def _rate(num: int, den: int) -> float:
    if den <= 0:
        raise ValueError("denominator must be positive")
    return num / den


def scan_population(train_source1: Path, ground_truth: Path, test_source1: Path) -> dict:
    country_by_anchor: dict[str, str] = {}
    train_country = Counter()
    with train_source1.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"entity_id", "country"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("unexpected train_source1 schema")
        for row in reader:
            anchor = row["entity_id"]
            country = row["country"]
            if anchor in country_by_anchor:
                raise ValueError(f"duplicate Source-1 anchor: {anchor}")
            country_by_anchor[anchor] = country
            train_country[country] += 1

    truth_hist: dict[str, Counter] = defaultdict(Counter)
    truth_rows = 0
    truth_edges = 0
    with ground_truth.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"source1_entity_id", "matched_entity_ids"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("unexpected ground_truth schema")
        seen_truth: set[str] = set()
        for row in reader:
            anchor = row["source1_entity_id"]
            if anchor in seen_truth:
                raise ValueError(f"duplicate truth anchor: {anchor}")
            seen_truth.add(anchor)
            country = country_by_anchor.get(anchor)
            if country is None:
                raise ValueError(f"truth anchor missing from Source-1: {anchor}")
            values = row["matched_entity_ids"].strip()
            cardinality = 0 if not values else values.count(",") + 1
            truth_hist[country][cardinality] += 1
            truth_rows += 1
            truth_edges += cardinality

    if truth_rows != len(country_by_anchor):
        raise ValueError(
            f"Source-1/truth anchor-count mismatch: {len(country_by_anchor)} vs {truth_rows}"
        )

    test_country = Counter()
    with test_source1.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"entity_id", "country"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("unexpected test_source1 schema")
        for row in reader:
            test_country[row["country"]] += 1

    def summarize(country: str) -> dict:
        hist = truth_hist[country]
        entities = train_country[country]
        edges = sum(k * n for k, n in hist.items())
        singletons = hist[0]
        return {
            "entities": entities,
            "truth_edges": edges,
            "mean_truth_cardinality": _rate(edges, entities),
            "singletons": singletons,
            "singleton_rate": _rate(singletons, entities),
            "cardinality_histogram": {str(k): hist[k] for k in sorted(hist)},
        }

    countries = {country: summarize(country) for country in sorted(train_country)}
    total_singletons = sum(v["singletons"] for v in countries.values())
    return {
        "train": {
            "entities": truth_rows,
            "truth_edges": truth_edges,
            "mean_truth_cardinality": _rate(truth_edges, truth_rows),
            "singletons": total_singletons,
            "singleton_rate": _rate(total_singletons, truth_rows),
            "countries": countries,
        },
        "test_source1": {
            "entities": sum(test_country.values()),
            "countries": dict(sorted(test_country.items())),
        },
    }


def derive_transfer(population: dict, v3: dict, v5: dict, france: dict, v6: dict) -> dict:
    test_counts = population["test_source1"]["countries"]
    required_test = {"US", "India", "France"}
    if set(test_counts) != required_test:
        raise ValueError(f"expected exactly {sorted(required_test)}, got {sorted(test_counts)}")
    total_test = population["test_source1"]["entities"]
    if v5["completion"]["validation"]["anchors"] != total_test:
        raise ValueError("V5 anchor count does not match complete test Source-1")
    if v6["rows"] != total_test:
        raise ValueError("V6 row count does not match complete test Source-1")
    additions = v6["added_by_country"]
    if sum(additions.values()) != v6["total_added"]:
        raise ValueError("V6 per-country additions do not sum to total_added")

    v3_countries = v3["countries"]
    if sum(x["entities"] for x in v3_countries.values()) != total_test:
        raise ValueError("V3 country entity counts do not match test population")
    if sum(x["new_matches"] for x in v3_countries.values()) != 5_819_438:
        raise ValueError("V3 country match counts do not reproduce committed export total")
    if sum(x["new_empty"] for x in v3_countries.values()) != 102_598:
        raise ValueError("V3 country empty counts do not reproduce committed export total")

    france_v5 = france["v5_neural32"]
    if france_v5["predicted_edges"] > v5["completion"]["validation"]["matches"]:
        raise ValueError("France V5 edges exceed total V5 edges")
    if france_v5["empty_predictions"] > v5["completion"]["validation"]["empty_predictions"]:
        raise ValueError("France V5 empty rows exceed total V5 empty rows")

    seen_n = test_counts["US"] + test_counts["India"]
    train = population["train"]["countries"]
    expected_seen_mean = (
        test_counts["US"] * train["US"]["mean_truth_cardinality"]
        + test_counts["India"] * train["India"]["mean_truth_cardinality"]
    ) / seen_n
    expected_seen_singleton = (
        test_counts["US"] * train["US"]["singleton_rate"]
        + test_counts["India"] * train["India"]["singleton_rate"]
    ) / seen_n

    def summary(matches: int, entities: int, empty: int | None = None) -> dict:
        out = {"entities": entities, "matches": matches, "mean_matches": matches / entities}
        if empty is not None:
            out.update({"empty_predictions": empty, "empty_rate": empty / entities})
        return out

    v3_seen_matches = v3_countries["US"]["new_matches"] + v3_countries["India"]["new_matches"]
    v3_seen_empty = v3_countries["US"]["new_empty"] + v3_countries["India"]["new_empty"]
    v5_total_matches = v5["completion"]["validation"]["matches"]
    v5_total_empty = v5["completion"]["validation"]["empty_predictions"]
    v5_seen_matches = v5_total_matches - france_v5["predicted_edges"]
    v5_seen_empty = v5_total_empty - france_v5["empty_predictions"]
    v6_seen_matches = v5_seen_matches + additions["US"] + additions["India"]

    fr_n = test_counts["France"]
    france_v3_matches = v3_countries["France"]["new_matches"]
    france_v3_empty = v3_countries["France"]["new_empty"]
    france_v6_matches = france_v5["predicted_edges"] + additions["France"]
    labeled_min_mean = min(
        train["US"]["mean_truth_cardinality"], train["India"]["mean_truth_cardinality"]
    )
    labeled_max_mean = max(
        train["US"]["mean_truth_cardinality"], train["India"]["mean_truth_cardinality"]
    )
    labeled_min_single = min(train["US"]["singleton_rate"], train["India"]["singleton_rate"])
    labeled_max_single = max(train["US"]["singleton_rate"], train["India"]["singleton_rate"])

    seen = {
        "test_entities": seen_n,
        "test_mix_expected_truth_mean": expected_seen_mean,
        "test_mix_expected_singleton_rate": expected_seen_singleton,
        "v3": summary(v3_seen_matches, seen_n, v3_seen_empty),
        "v5": summary(v5_seen_matches, seen_n, v5_seen_empty),
        "v6": summary(v6_seen_matches, seen_n, None),
        "v5_minus_v3_edges": v5_seen_matches - v3_seen_matches,
        "v6_minus_v5_edges": v6_seen_matches - v5_seen_matches,
    }
    for key in ("v3", "v5", "v6"):
        seen[key]["mean_gap_vs_train_test_mix"] = seen[key]["mean_matches"] - expected_seen_mean
    for key in ("v3", "v5"):
        seen[key]["empty_gap_vs_train_test_mix"] = (
            seen[key]["empty_rate"] - expected_seen_singleton
        )

    france_out = {
        "test_entities": fr_n,
        "labeled_truth_mean_range": [labeled_min_mean, labeled_max_mean],
        "labeled_singleton_rate_range": [labeled_min_single, labeled_max_single],
        "v3": summary(france_v3_matches, fr_n, france_v3_empty),
        "v5": summary(france_v5["predicted_edges"], fr_n, france_v5["empty_predictions"]),
        "v6": summary(france_v6_matches, fr_n, None),
        "v5_minus_v3_edges": france_v5["predicted_edges"] - france_v3_matches,
        "v6_minus_v5_edges": additions["France"],
    }
    for key in ("v3", "v5", "v6"):
        mean = france_out[key]["mean_matches"]
        if mean < labeled_min_mean:
            distance = mean - labeled_min_mean
        elif mean > labeled_max_mean:
            distance = mean - labeled_max_mean
        else:
            distance = 0.0
        france_out[key]["mean_distance_to_labeled_range"] = distance
    for key in ("v3", "v5"):
        rate = france_out[key]["empty_rate"]
        if rate < labeled_min_single:
            distance = rate - labeled_min_single
        elif rate > labeled_max_single:
            distance = rate - labeled_max_single
        else:
            distance = 0.0
        france_out[key]["empty_distance_to_labeled_range"] = distance

    total_v3 = summary(5_819_438, total_test, 102_598)
    total_v5 = summary(v5_total_matches, total_test, v5_total_empty)
    total_v6 = summary(v5_total_matches + v6["total_added"], total_test, None)

    return {
        "seen_countries_US_India": seen,
        "france_unlabeled": france_out,
        "overall_descriptive_only": {"v3": total_v3, "v5": total_v5, "v6": total_v6},
        "artifact_limitations": [
            "Committed V5 artifacts do not expose India and US test match/empty counts separately; only their exact combined totals are derivable after subtracting France.",
            "V6 receipt gives added links by country but not changed-row or empty-row reductions by country, so V6 empty rates cannot be reconstructed exactly.",
            "France has no supplied labels; distance to the US/India truth range is a drift diagnostic, not an accuracy estimate.",
        ],
    }


def run(args: argparse.Namespace) -> dict:
    started = time.monotonic()
    population = scan_population(args.train_source1, args.ground_truth, args.test_source1)
    with args.v3_country.open(encoding="utf-8") as handle:
        v3 = json.load(handle)
    with args.v5_submission.open(encoding="utf-8") as handle:
        v5 = json.load(handle)
    with args.france_audit.open(encoding="utf-8") as handle:
        france = json.load(handle)
    with args.v6_submission.open(encoding="utf-8") as handle:
        v6 = json.load(handle)
    return {
        "experiment": "X015",
        "protocol": (
            "Full train Source-1 + truth census; complete test Source-1 country counts; "
            "committed unlabeled V3/V5/V6 aggregate outputs only"
        ),
        "population": population,
        "transfer": derive_transfer(population, v3, v5, france, v6),
        "runtime_seconds": time.monotonic() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-source1", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--test-source1", type=Path, required=True)
    parser.add_argument("--v3-country", type=Path, required=True)
    parser.add_argument("--v5-submission", type=Path, required=True)
    parser.add_argument("--france-audit", type=Path, required=True)
    parser.add_argument("--v6-submission", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "train_entities": result["population"]["train"]["entities"],
        "test_entities": result["population"]["test_source1"]["entities"],
        "seen_v3_mean": result["transfer"]["seen_countries_US_India"]["v3"]["mean_matches"],
        "seen_v5_mean": result["transfer"]["seen_countries_US_India"]["v5"]["mean_matches"],
        "france_v3_mean": result["transfer"]["france_unlabeled"]["v3"]["mean_matches"],
        "france_v5_mean": result["transfer"]["france_unlabeled"]["v5"]["mean_matches"],
        "runtime_seconds": result["runtime_seconds"],
    }, indent=2))


if __name__ == "__main__":
    main()
