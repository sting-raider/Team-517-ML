#!/usr/bin/env python3
"""Decompose entity-level F0.5 deficit into retrieval-ceiling and within-candidate loss.

This helper uses only aggregate evaluation JSON. It never reads challenge rows.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def decompose(score: float, oracle: float, target: float = 0.998) -> dict[str, float]:
    if not (0.0 <= score <= oracle <= 1.0):
        raise ValueError(f"expected 0 <= score <= oracle <= 1, got score={score}, oracle={oracle}")
    if not (0.0 <= target <= 1.0):
        raise ValueError(f"target must be in [0, 1], got {target}")
    total = 1.0 - score
    retrieval = 1.0 - oracle
    within = oracle - score
    result = {
        "score": score,
        "oracle": oracle,
        "total_deficit": total,
        "retrieval_ceiling_loss": retrieval,
        "within_candidate_loss": within,
        "retrieval_share_of_deficit": retrieval / total if total else 0.0,
        "within_candidate_share_of_deficit": within / total if total else 0.0,
        "oracle_shortfall_to_target": max(0.0, target - oracle),
    }
    result["fraction_of_current_retrieval_loss_to_remove_for_target_oracle"] = (
        result["oracle_shortfall_to_target"] / retrieval if retrieval else 0.0
    )
    return result


def transition(old_score: float, old_oracle: float, new_score: float, new_oracle: float) -> dict[str, float]:
    old = decompose(old_score, old_oracle)
    new = decompose(new_score, new_oracle)
    score_gain = new_score - old_score
    oracle_gain = new_oracle - old_oracle
    within_gap_reduction = old["within_candidate_loss"] - new["within_candidate_loss"]
    out = {
        "score_gain": score_gain,
        "oracle_gain": oracle_gain,
        "within_candidate_gap_reduction": within_gap_reduction,
    }
    if score_gain:
        out["oracle_gain_share_of_score_gain"] = oracle_gain / score_gain
        out["within_gap_reduction_share_of_score_gain"] = within_gap_reduction / score_gain
    return out


def _load_v3(path: Path) -> dict:
    return json.loads(path.read_text())["new"]["holdout"]


def _load_v5(path: Path, variant: str) -> dict:
    data = json.loads(path.read_text())
    for item in data["variants"]:
        if item.get("name") == variant:
            return item["holdout"]
    raise KeyError(f"variant {variant!r} not found")


def build_report(v3: dict, v5: dict, v6_score: float, target: float = 0.998) -> dict:
    slices: dict[str, dict] = {}
    for name in ("all", "India", "US"):
        old = v3[name]
        new = v5[name]
        slices[name] = {
            "entities": int(new["entities"]),
            "v3": decompose(float(old["macro_f0_5"]), float(old["blocking_oracle_macro_f0_5"]), target),
            "v5": decompose(float(new["macro_f0_5"]), float(new["blocking_oracle_macro_f0_5"]), target),
            "v3_to_v5": transition(
                float(old["macro_f0_5"]),
                float(old["blocking_oracle_macro_f0_5"]),
                float(new["macro_f0_5"]),
                float(new["blocking_oracle_macro_f0_5"]),
            ),
        }
    v5_all = v5["all"]
    v6 = decompose(v6_score, float(v5_all["blocking_oracle_macro_f0_5"]), target)
    v5_within = slices["all"]["v5"]["within_candidate_loss"]
    v6_gain = v6_score - float(v5_all["macro_f0_5"])
    return {
        "target": target,
        "slices": slices,
        "v6_overall": v6,
        "v6_gain_over_v5": v6_gain,
        "v6_fraction_of_v5_within_candidate_gap_closed": v6_gain / v5_within if v5_within else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v3-json", type=Path, required=True)
    parser.add_argument("--v5-json", type=Path, required=True)
    parser.add_argument("--v5-variant", default="dense_prior_-2")
    parser.add_argument("--v6-score", type=float, required=True)
    parser.add_argument("--target", type=float, default=0.998)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_report(
        _load_v3(args.v3_json),
        _load_v5(args.v5_json, args.v5_variant),
        args.v6_score,
        args.target,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
