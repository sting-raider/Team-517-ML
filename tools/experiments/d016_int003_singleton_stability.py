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


def load_slices(train_report: dict, confirmation: dict, model_key: str) -> dict:
    if model_key == "v3":
        cal = train_report["new"]["calibrate"]
        hold = train_report["new"]["holdout"]
        conf = confirmation["new"]
    elif model_key == "v2_fused":
        cal = train_report["baseline"]["calibrate"]
        hold = train_report["baseline"]["holdout"]
        conf = confirmation["baseline_v2_fused_pool"]
    else:
        raise ValueError(model_key)
    return {
        "calibrate": {c: extract_metric(cal[c]) for c in COUNTRIES},
        "holdout": {c: extract_metric(hold[c]) for c in COUNTRIES},
        "confirmation": {c: extract_metric(conf[c]) for c in COUNTRIES},
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
    v3 = load_slices(train_report, confirmation, "v3")
    v2 = load_slices(train_report, confirmation, "v2_fused")
    pooled = {}
    same_pool_delta = {}
    for country in COUNTRIES:
        p3 = pooled_descriptive(v3, country)
        p2 = pooled_descriptive(v2, country)
        pooled[country] = {
            "v3": p3,
            "v2_fused": p2,
            "v3_minus_v2_fused_rate_pp": 100.0 * (p3["false_positive_rate"] - p2["false_positive_rate"]),
        }
        same_pool_delta[country] = {}
        for split in SLICES:
            a, b = v3[split][country], v2[split][country]
            score_gain = a["macro_f0_5"] - b["macro_f0_5"]
            singleton_penalty = (a["false_positives"] - b["false_positives"]) / a["entities"]
            same_pool_delta[country][split] = {
                "v3_minus_v2_fused_fp_count": a["false_positives"] - b["false_positives"],
                "v3_minus_v2_fused_singleton_component": -singleton_penalty,
                "v3_minus_v2_fused_macro_gain": score_gain,
                "non_singleton_net_component": score_gain + singleton_penalty,
            }

    conf = v3["confirmation"]
    confirmation_headroom = {}
    for country in COUNTRIES:
        row = conf[country]
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
        "v3": v3,
        "v2_fused": v2,
        "pooled_descriptive": pooled,
        "same_fused_pool_retraining_attribution": same_pool_delta,
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
