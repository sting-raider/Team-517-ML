#!/usr/bin/env python3
"""I032: bounded post-hoc analysis of INT003 local-to-public score gap.

This helper deliberately treats a leaderboard score as a scalar diagnostic only.
It does not use leaderboard feedback as labels, tune any model/threshold, or infer
French correctness. All score-mixture results are conditional identities.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Mapping


def scan_country_counts(path: Path) -> tuple[int, dict[str, int], str]:
    """Stream a Source-1 TSV and return row count, country counts, SHA-256."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            digest.update(block)

    counts: Counter[str] = Counter()
    rows = 0
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if reader.fieldnames is None or "country" not in reader.fieldnames:
            raise ValueError("TSV must contain a 'country' column")
        for row in reader:
            rows += 1
            counts[row["country"]] += 1
    return rows, dict(sorted(counts.items())), digest.hexdigest()


def weighted_mean(values: Mapping[str, float], counts: Mapping[str, int]) -> float:
    missing = set(counts) - set(values)
    if missing:
        raise ValueError(f"missing values for groups: {sorted(missing)}")
    total = sum(counts.values())
    if total <= 0:
        raise ValueError("counts must sum to a positive value")
    return sum(float(values[k]) * int(v) for k, v in counts.items()) / total


def required_group_score(overall: float, group_weight: float, other_score: float) -> float:
    """Solve overall = w*group + (1-w)*other for group."""
    if not 0.0 < group_weight <= 1.0:
        raise ValueError("group_weight must be in (0, 1]")
    return (overall - (1.0 - group_weight) * other_score) / group_weight


def required_other_score(overall: float, group_weight: float, group_score: float) -> float:
    """Solve overall = w*group + (1-w)*other for other."""
    if not 0.0 <= group_weight < 1.0:
        raise ValueError("group_weight must be in [0, 1)")
    return (overall - group_weight * group_score) / (1.0 - group_weight)


def two_sample_hoeffding_bound(delta: float, n_a: int, n_b: int) -> float:
    """Two-sided Hoeffding upper bound for two [0,1] sample means.

    Conditional on both samples being independent draws from the same population:
      P(|mean(A)-mean(B)| >= delta) <=
        2 exp(-2 delta^2 / (1/n_a + 1/n_b)).
    """
    if n_a <= 0 or n_b <= 0:
        raise ValueError("sample sizes must be positive")
    d = abs(float(delta))
    denom = 1.0 / n_a + 1.0 / n_b
    return min(1.0, 2.0 * math.exp(-2.0 * d * d / denom))


def minimum_second_sample_for_hoeffding(
    delta: float, n_a: int, alpha: float = 0.05
) -> int | None:
    """Smallest n_b making the two-sample Hoeffding bound <= alpha.

    Returns None if even n_b -> infinity cannot reach alpha.
    """
    if n_a <= 0 or not 0.0 < alpha < 1.0:
        raise ValueError("invalid n_a/alpha")
    d = abs(float(delta))
    if d == 0.0:
        return None
    max_denom = 2.0 * d * d / math.log(2.0 / alpha)
    remainder = max_denom - 1.0 / n_a
    if remainder <= 0.0:
        return None
    return math.ceil(1.0 / remainder)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def analyze(
    test_source1: Path,
    confirmation_json: Path,
    int003_json: Path,
    public_score: float,
) -> dict:
    if not 0.0 <= public_score <= 1.0:
        raise ValueError("public_score must be in [0,1]")

    rows, country_counts, sha256 = scan_country_counts(test_source1)
    required = {"France", "India", "US"}
    if set(country_counts) != required:
        raise ValueError(f"expected exactly {sorted(required)}, got {sorted(country_counts)}")

    confirm = _load_json(confirmation_json)
    current = _load_json(int003_json)
    new = confirm["new"]
    conf_all = float(new["all"]["macro_f0_5"])
    conf_country = {
        "India": float(new["India"]["macro_f0_5"]),
        "US": float(new["US"]["macro_f0_5"]),
    }
    conf_n = int(new["all"]["entities"])

    non_france_counts = {k: country_counts[k] for k in ("India", "US")}
    non_france_score = weighted_mean(conf_country, non_france_counts)
    france_weight = country_counts["France"] / rows
    required_france = required_group_score(public_score, france_weight, non_france_score)

    local_slices = {
        "calibration": float(current["new"]["calibrate"]["all"]["macro_f0_5"]),
        "development_holdout": float(current["new"]["holdout"]["all"]["macro_f0_5"]),
        "frozen_confirmation": conf_all,
    }

    share_sensitivity = []
    for share in (0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        share_sensitivity.append(
            {
                "public_france_share": share,
                "required_france_score_if_non_france_unchanged": required_group_score(
                    public_score, share, non_france_score
                ),
            }
        )

    france_score_sensitivity = []
    for score in (0.0, 0.5, 0.7, 0.75, 0.8, 0.85, 0.9, conf_country["India"], 0.95):
        france_score_sensitivity.append(
            {
                "assumed_france_score": score,
                "required_non_france_score_at_full_test_mix": required_other_score(
                    public_score, france_weight, score
                ),
            }
        )

    gap = conf_all - public_score
    min_public_n = minimum_second_sample_for_hoeffding(gap, conf_n, alpha=0.05)

    paired = confirm.get("paired_comparison", {})
    return {
        "experiment_id": "I032",
        "reported_public_score": public_score,
        "leaderboard_usage": "post-hoc scalar diagnostic only; not labels or tuning target",
        "test_source1": {
            "rows": rows,
            "sha256": sha256,
            "country_counts": country_counts,
            "country_shares": {k: v / rows for k, v in country_counts.items()},
        },
        "local_int003": {
            "slices": local_slices,
            "confirmation_country_scores": conf_country,
            "confirmation_entities": conf_n,
            "paired_v3_minus_v2_bootstrap_95_interval": paired.get("bootstrap_95_interval"),
            "paired_interval_scope_warning": (
                "This interval is for the paired v3-v2 delta, not an absolute "
                "confidence interval for the v3 macro score."
            ),
        },
        "gap": {
            "confirmation_minus_reported_public": gap,
            "public_minus_local_slices": {
                k: public_score - v for k, v in local_slices.items()
            },
            "same_population_sampling_check": {
                "interpretation": (
                    "Conditional only: if confirmation and public rows were independent "
                    "random samples from the same score distribution. Public split size "
                    "and composition are not disclosed here."
                ),
                "minimum_public_entities_for_two_sample_hoeffding_p_le_0_05": min_public_n,
                "bound_if_public_entities_equal_confirmation_entities": two_sample_hoeffding_bound(
                    gap, conf_n, conf_n
                ),
            },
        },
        "full_test_mix_counterfactual": {
            "france_weight": france_weight,
            "non_france_confirmation_score_reweighted_to_test_india_us_mix": non_france_score,
            "required_france_score_for_reported_public_if_non_france_unchanged": required_france,
            "overall_if_france_equals_india_confirmation": (
                (1.0 - france_weight) * non_france_score
                + france_weight * conf_country["India"]
            ),
            "overall_if_france_equals_non_france": non_france_score,
            "france_only_explanation_is_arithmetically_possible": 0.0 <= required_france <= 1.0,
        },
        "public_france_share_sensitivity": share_sensitivity,
        "france_score_sensitivity_full_test_mix": france_score_sensitivity,
        "limitations": [
            "The public leaderboard country composition and entity count are not established by this analysis.",
            "France has no supplied labels; every France score shown is a counterfactual algebraic requirement, not an estimate.",
            "The reported public score is not used to select a threshold, model, retrieval rule, or feature.",
            "Different test/public distributions, retrieval shift, matcher shift, decision shift, or mixtures of them can produce the same aggregate gap.",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--test-source1", type=Path, required=True)
    p.add_argument(
        "--confirmation-json",
        type=Path,
        default=Path("reports/int003_depth10_confirmation.json"),
    )
    p.add_argument(
        "--int003-json", type=Path, default=Path("reports/int003_depth10.json")
    )
    p.add_argument("--public-score", type=float, default=0.917)
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    result = analyze(
        args.test_source1, args.confirmation_json, args.int003_json, args.public_score
    )
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
