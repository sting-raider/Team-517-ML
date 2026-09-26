from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

SLICES = ("calibrate", "holdout", "confirmation")
COUNTRIES = ("all", "India", "US")


def exact_fp_count(singleton_count: int, rate: float, tol: float = 1e-9) -> int:
    value = singleton_count * rate
    count = int(round(value))
    if abs(value - count) > tol:
        raise ValueError(f"rate does not encode an exact count: n={singleton_count}, rate={rate}")
    return count


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("total must be positive")
    p = successes / total
    den = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / den
    half = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / den
    return center - half, center + half


def extract_metric(row: dict) -> dict:
    n = int(row["singleton_count"])
    fp = exact_fp_count(n, float(row["singleton_false_positive_rate"]))
    entities = int(row["entities"])
    low, high = wilson_interval(fp, n)
    return {
        "entities": entities,
        "singleton_count": n,
        "false_positives": fp,
        "false_positive_rate": fp / n,
        "wilson95": [low, high],
        "perfect_singleton_fix_macro_headroom": fp / entities,
        "macro_f0_5": float(row["macro_f0_5"]),
        "blocking_oracle_macro_f0_5": float(row["blocking_oracle_macro_f0_5"]),
    }


def load_v3_slices(train_report: dict, confirmation: dict) -> dict:
    sources = {
        "calibrate": train_report["new"]["calibrate"],
        "holdout": train_report["new"]["holdout"],
        "confirmation": confirmation["new"],
    }
    return {
        split: {country: extract_metric(rows[country]) for country in COUNTRIES}
        for split, rows in sources.items()
    }


def pooled_descriptive(rows: dict, country: str) -> dict:
    fp = sum(rows[s][country]["false_positives"] for s in SLICES)
    singletons = sum(rows[s][country]["singleton_count"] for s in SLICES)
    low, high = wilson_interval(fp, singletons)
    rates = [rows[s][country]["false_positive_rate"] for s in SLICES]
    return {
        "false_positives": fp,
        "singleton_count": singletons,
        "false_positive_rate": fp / singletons,
        "wilson95": [low, high],
        "split_min_rate": min(rates),
        "split_max_rate": max(rates),
        "split_range_pp": 100.0 * (max(rates) - min(rates)),
        "warning": "descriptive pool only; calibration/holdout are reused development slices, not independent confirmation",
    }


def analyze(train_report: dict, confirmation: dict) -> dict:
    v3 = load_v3_slices(train_report, confirmation)
    pooled = {country: pooled_descriptive(v3, country) for country in COUNTRIES}

    confirmation_headroom = {}
    for country in COUNTRIES:
        row = v3["confirmation"][country]
        total_deficit = 1.0 - row["macro_f0_5"]
        within = row["blocking_oracle_macro_f0_5"] - row["macro_f0_5"]
        headroom = row["perfect_singleton_fix_macro_headroom"]
        confirmation_headroom[country] = {
            "perfect_fix_macro_headroom": headroom,
            "share_of_total_deficit": headroom / total_deficit,
            "share_of_within_candidate_gap": headroom / within,
            "total_deficit": total_deficit,
            "within_candidate_gap": within,
        }

    return {
        "experiment_id": "D016",
        "recommendation": "FOLLOW-UP",
        "protocol": "committed INT003 aggregate artifacts only; no new labels/probabilities/tuning",
        "dependency_correction": {
            "status": "WITHDRAWN_COMPARISON",
            "reason": "I028 found baseline_v2_fused_pool used v3 relative_retrieval_score semantics; it is not a feature-contract-pure frozen-v2 counterfactual",
            "invalidated_outputs": [
                "v2_fused pooled singleton comparison",
                "same-fused-pool retraining attribution",
                "derived non-singleton retraining component",
            ],
            "unaffected_outputs": [
                "INT003 singleton counts/rates",
                "Wilson intervals",
                "cross-slice descriptive stability",
                "perfect singleton-fix headroom",
                "I027 current-v3 actual-vs-oracle error budget",
            ],
        },
        "v3": v3,
        "pooled_descriptive": pooled,
        "confirmation_headroom": confirmation_headroom,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train-report", type=Path, default=Path("reports/int003_depth10.json"))
    p.add_argument("--confirmation", type=Path, default=Path("reports/int003_depth10_confirmation.json"))
    p.add_argument("--out", type=Path, default=Path("reports/swarm/D016-int003-singleton-stability.json"))
    args = p.parse_args()
    train_report = json.loads(args.train_report.read_text(encoding="utf-8"))
    confirmation = json.loads(args.confirmation.read_text(encoding="utf-8"))
    result = analyze(train_report, confirmation)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
