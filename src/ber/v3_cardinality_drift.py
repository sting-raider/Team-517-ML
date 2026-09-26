"""Audit INT003 test prediction cardinality against labeled train truth priors.

This is an aggregate robustness diagnostic, not a test-label estimator.  It reads only
supplied training Source-1/truth records plus the committed unlabeled INT003 country
output aggregates.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def _truth_summary(counter: Counter[int]) -> dict:
    anchors = sum(counter.values())
    edges = sum(k * v for k, v in counter.items())
    singleton_count = counter.get(0, 0)
    return {
        "anchors": anchors,
        "positive_edges": edges,
        "mean_true_matches": edges / anchors if anchors else None,
        "singleton_count": singleton_count,
        "singleton_rate": singleton_count / anchors if anchors else None,
        "cardinality_counts": {str(k): counter[k] for k in sorted(counter)},
    }


def build_train_priors(source1: Path, truth: Path) -> dict:
    country_by_id: dict[str, str] = {}
    country_counts: Counter[str] = Counter()
    with source1.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            entity_id = row["entity_id"]
            country = row["country"]
            if entity_id in country_by_id:
                raise ValueError(f"duplicate Source-1 entity_id: {entity_id}")
            country_by_id[entity_id] = country
            country_counts[country] += 1

    overall: Counter[int] = Counter()
    by_country: dict[str, Counter[int]] = defaultdict(Counter)
    seen: set[str] = set()
    unknown_truth = 0
    with truth.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            entity_id = row["source1_entity_id"]
            if entity_id in seen:
                raise ValueError(f"duplicate truth row: {entity_id}")
            seen.add(entity_id)
            raw = row.get("matched_entity_ids") or ""
            cardinality = sum(1 for x in raw.split(",") if x.strip()) if raw else 0
            country = country_by_id.get(entity_id)
            if country is None:
                unknown_truth += 1
                continue
            overall[cardinality] += 1
            by_country[country][cardinality] += 1

    missing_truth = len(country_by_id) - len(seen & country_by_id.keys())
    if unknown_truth or missing_truth:
        raise ValueError(
            f"truth/source1 mismatch: unknown_truth={unknown_truth}, missing_truth={missing_truth}"
        )

    return {
        "source1_country_counts": dict(sorted(country_counts.items())),
        "overall": _truth_summary(overall),
        "by_country": {
            country: _truth_summary(counter)
            for country, counter in sorted(by_country.items())
        },
    }


def _prediction_summary(raw: dict) -> dict:
    entities = int(raw["entities"])
    return {
        "entities": entities,
        "v2_mean_predictions": raw["baseline_matches"] / entities,
        "v3_mean_predictions": raw["new_matches"] / entities,
        "v2_empty_rate": raw["baseline_empty"] / entities,
        "v3_empty_rate": raw["new_empty"] / entities,
        "v2_matches": int(raw["baseline_matches"]),
        "v3_matches": int(raw["new_matches"]),
        "v2_empty": int(raw["baseline_empty"]),
        "v3_empty": int(raw["new_empty"]),
    }


def compare(train: dict, test_drift: dict) -> dict:
    predictions = {
        country: _prediction_summary(raw)
        for country, raw in test_drift["countries"].items()
    }

    comparisons = {}
    for country in ("India", "US"):
        if country not in train["by_country"] or country not in predictions:
            continue
        prior = train["by_country"][country]
        pred = predictions[country]
        train_mean = prior["mean_true_matches"]
        train_singleton = prior["singleton_rate"]
        v2_mean_gap = pred["v2_mean_predictions"] - train_mean
        v3_mean_gap = pred["v3_mean_predictions"] - train_mean
        v2_empty_gap = pred["v2_empty_rate"] - train_singleton
        v3_empty_gap = pred["v3_empty_rate"] - train_singleton
        comparisons[country] = {
            "train_mean_true_matches": train_mean,
            "train_singleton_rate": train_singleton,
            **pred,
            "v2_mean_gap": v2_mean_gap,
            "v3_mean_gap": v3_mean_gap,
            "mean_abs_gap_reduction_fraction":
                (abs(v2_mean_gap) - abs(v3_mean_gap)) / abs(v2_mean_gap)
                if v2_mean_gap else None,
            "v2_empty_gap": v2_empty_gap,
            "v3_empty_gap": v3_empty_gap,
            "empty_abs_gap_reduction_fraction":
                (abs(v2_empty_gap) - abs(v3_empty_gap)) / abs(v2_empty_gap)
                if v2_empty_gap else None,
            "v3_counterfactual_edge_gap_if_train_mean_transported":
                pred["v3_matches"] - train_mean * pred["entities"],
        }

    labeled = [train["by_country"][c] for c in ("India", "US")]
    mean_lo = min(x["mean_true_matches"] for x in labeled)
    mean_hi = max(x["mean_true_matches"] for x in labeled)
    singleton_lo = min(x["singleton_rate"] for x in labeled)
    singleton_hi = max(x["singleton_rate"] for x in labeled)

    france = predictions.get("France")
    france_diag = None
    if france is not None:
        france_diag = {
            **france,
            "labeled_mean_envelope": [mean_lo, mean_hi],
            "v3_mean_gap_above_labeled_envelope": france["v3_mean_predictions"] - mean_hi,
            "v3_match_excess_vs_labeled_mean_envelope_if_transported": [
                france["v3_matches"] - mean_hi * france["entities"],
                france["v3_matches"] - mean_lo * france["entities"],
            ],
            "labeled_singleton_envelope": [singleton_lo, singleton_hi],
            "v3_empty_gap_below_labeled_envelope": france["v3_empty_rate"] - singleton_lo,
        }

    total_entities = sum(x["entities"] for x in predictions.values())
    total_v2 = sum(x["v2_matches"] for x in predictions.values())
    total_v3 = sum(x["v3_matches"] for x in predictions.values())
    return {
        "train_priors": train,
        "test_predictions": predictions,
        "same_country_transport_diagnostic": comparisons,
        "france_unlabeled_diagnostic": france_diag,
        "overall_test": {
            "entities": total_entities,
            "v2_matches": total_v2,
            "v3_matches": total_v3,
            "v2_mean_predictions": total_v2 / total_entities,
            "v3_mean_predictions": total_v3 / total_entities,
            "train_overall_mean_true_matches": train["overall"]["mean_true_matches"],
            "v3_minus_train_overall_mean":
                total_v3 / total_entities - train["overall"]["mean_true_matches"],
        },
        "interpretation_guard":
            "Prediction cardinality versus train truth cardinality is a transport diagnostic only; "
            "test truth, especially France truth, is unknown.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source1", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--test-drift", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    train = build_train_priors(args.source1, args.truth)
    drift = json.loads(args.test_drift.read_text(encoding="utf-8"))
    result = compare(train, drift)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
