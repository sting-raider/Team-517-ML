"""Decompose an entity-level F0.5 report into retrieval and decision headroom."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def decompose_slice(metrics: dict, target: float = 0.998) -> dict:
    n = int(metrics["entities"])
    score = float(metrics["macro_f0_5"])
    oracle = float(metrics["blocking_oracle_macro_f0_5"])
    singletons = int(metrics["singleton_count"])
    sfpr = float(metrics["singleton_false_positive_rate"])
    if not (0 <= score <= oracle <= 1):
        raise ValueError(f"expected 0 <= score <= oracle <= 1, got {score=}, {oracle=}")
    if not (0 <= singletons <= n and 0 <= sfpr <= 1):
        raise ValueError("invalid singleton statistics")
    fp_float = singletons * sfpr
    singleton_fp_count = int(round(fp_float))
    if not math.isclose(fp_float, singleton_fp_count, abs_tol=1e-8):
        raise ValueError("singleton FPR does not correspond to an integer false-positive count")

    total_gap = 1.0 - score
    retrieval_gap = 1.0 - oracle
    decision_gap = oracle - score
    singleton_gain = singleton_fp_count / n
    target_oracle_gain = max(0.0, target - oracle)
    return {
        "entities": n,
        "score": score,
        "blocking_oracle": oracle,
        "gap_to_perfect": total_gap,
        "retrieval_ceiling_gap": retrieval_gap,
        "within_candidate_model_decision_gap": decision_gap,
        "fraction_total_gap_retrieval_ceiling": retrieval_gap / total_gap if total_gap else 0.0,
        "fraction_total_gap_model_decision": decision_gap / total_gap if total_gap else 0.0,
        "singleton_false_positive_count": singleton_fp_count,
        "oracle_singleton_only_gain": singleton_gain,
        "singleton_gain_fraction_total_gap": singleton_gain / total_gap if total_gap else 0.0,
        "singleton_gain_fraction_model_decision_gap": singleton_gain / decision_gap if decision_gap else 0.0,
        "target": target,
        "minimum_oracle_gain_for_target": target_oracle_gain,
        "fraction_current_retrieval_gap_that_must_close_for_target":
            target_oracle_gain / retrieval_gap if retrieval_gap else 0.0,
    }


def decompose_report(report: dict, target: float = 0.998) -> dict:
    scores = report["scores"]
    result = {name: decompose_slice(metrics, target) for name, metrics in scores.items()}
    all_row = result["all"]
    countries = [name for name in scores if name != "all"]
    if sum(result[name]["entities"] for name in countries) == all_row["entities"]:
        weights = {name: result[name]["entities"] / all_row["entities"] for name in countries}
        checks = {}
        for field in ("score", "blocking_oracle"):
            weighted = sum(weights[name] * result[name][field] for name in countries)
            checks[field] = {
                "weighted_country_value": weighted,
                "all_value": all_row[field],
                "abs_error": abs(weighted - all_row[field]),
            }
        contributions = {}
        for gap in ("gap_to_perfect", "retrieval_ceiling_gap", "within_candidate_model_decision_gap"):
            weighted = {name: weights[name] * result[name][gap] for name in countries}
            total = sum(weighted.values())
            contributions[gap] = {
                name: {
                    "absolute_macro_contribution": value,
                    "share_of_gap": value / total if total else 0.0,
                }
                for name, value in weighted.items()
            }
        result["country_weighting_checks"] = checks
        result["country_gap_contributions"] = contributions
    return result


def cap_conversion(wide: dict, low: str = "retrieval_80", high: str = "retrieval_640") -> dict:
    lo, hi = wide[low], wide[high]
    model_gain = float(hi["macro_f0_5"]) - float(lo["macro_f0_5"])
    oracle_gain = float(hi["blocking_oracle_macro_f0_5"]) - float(lo["blocking_oracle_macro_f0_5"])
    return {
        "low": low,
        "high": high,
        "model_macro_gain": model_gain,
        "oracle_macro_gain": oracle_gain,
        "historical_realized_fraction_of_added_oracle_headroom":
            model_gain / oracle_gain if oracle_gain else None,
        "singleton_fpr_delta":
            float(hi["singleton_false_positive_rate"]) - float(lo["singleton_false_positive_rate"]),
        "pair_recall_delta":
            float(hi["candidate_pair_recall"]) - float(lo["candidate_pair_recall"]),
        "warning":
            "Calibration-only historical matcher evidence; do not treat as selected-confirmation performance.",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--confirmation", type=Path, required=True)
    p.add_argument("--wide-calibration", type=Path)
    p.add_argument("--target", type=float, default=0.998)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    report = json.loads(a.confirmation.read_text(encoding="utf-8"))
    result = {"selected_confirmation": decompose_report(report, a.target)}
    if a.wide_calibration:
        result["calibration_cap_context"] = cap_conversion(
            json.loads(a.wide_calibration.read_text(encoding="utf-8"))
        )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
