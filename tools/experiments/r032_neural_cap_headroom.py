"""R032: aggregate-only INT005/INT006 candidate-cap headroom analysis."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

KEY = re.compile(r"^cap(?P<cap>\d+)_dense(?P<dense>\d+)$")


def combine_variant(india: dict, us: dict, truth_links: dict[str, int], key: str) -> dict:
    vi, vu = india["variants"][key], us["variants"][key]
    ai, au = int(india["anchors"]), int(us["anchors"])
    ti, tu = int(truth_links["India"]), int(truth_links["US"])
    m = KEY.match(key)
    if not m:
        raise ValueError(f"Bad variant key: {key}")
    pair = (vi["candidate_pair_recall"] * ti + vu["candidate_pair_recall"] * tu) / (ti + tu)
    oracle = (vi["blocking_oracle_macro_f0_5"] * ai + vu["blocking_oracle_macro_f0_5"] * au) / (ai + au)
    return {
        "variant": key,
        "cap": int(m.group("cap")),
        "dense": int(m.group("dense")),
        "candidate_pair_recall": pair,
        "blocking_oracle_macro_f0_5": oracle,
        "India_oracle": vi["blocking_oracle_macro_f0_5"],
        "US_oracle": vu["blocking_oracle_macro_f0_5"],
    }


def calibration_pick(rows: list[dict]) -> dict[int, dict]:
    picked = {}
    for row in rows:
        cap = row["cap"]
        old = picked.get(cap)
        if old is None or (row["blocking_oracle_macro_f0_5"], -row["dense"]) > (
            old["blocking_oracle_macro_f0_5"], -old["dense"]
        ):
            picked[cap] = row
    return picked


def analyze(cal_i: dict, cal_u: dict, hold_i: dict, hold_u: dict, error_budget: dict) -> dict:
    truth_cal = {
        "India": error_budget["calibrate_India"]["truth_links"],
        "US": error_budget["calibrate_US"]["truth_links"],
    }
    truth_hold = {
        "India": error_budget["holdout_India"]["truth_links"],
        "US": error_budget["holdout_US"]["truth_links"],
    }
    keys = sorted(set(cal_i["variants"]) & set(cal_u["variants"]) &
                  set(hold_i["variants"]) & set(hold_u["variants"]))
    cal = [combine_variant(cal_i, cal_u, truth_cal, k) for k in keys]
    hold = {r["variant"]: r for r in
            (combine_variant(hold_i, hold_u, truth_hold, k) for k in keys)}
    picks = calibration_pick(cal)
    selected = []
    base = None
    for cap in sorted(picks):
        c = picks[cap]
        h = hold[c["variant"]]
        if cap == 32:
            base = h
        selected.append({
            "calibration": c,
            "holdout": h,
            "pair_cost_multiple_vs_cap32": cap / 32.0,
        })
    if base is None:
        raise ValueError("Missing cap32 baseline")
    for row in selected:
        h = row["holdout"]
        h["delta_pair_recall_vs_cap32"] = (
            h["candidate_pair_recall"] - base["candidate_pair_recall"]
        )
        h["delta_oracle_vs_cap32"] = (
            h["blocking_oracle_macro_f0_5"] - base["blocking_oracle_macro_f0_5"]
        )
    fixed_dense16 = []
    for cap in (32, 64, 128, 160):
        key = f"cap{cap}_dense16"
        if key in hold:
            fixed_dense16.append({
                "calibration": next(r for r in cal if r["variant"] == key),
                "holdout": hold[key],
            })
    return {
        "calibration_selected_per_cap": selected,
        "fixed_dense16": fixed_dense16,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = args.report_dir
    cal_i = json.loads((root / "int005_capped_india.json").read_text())
    cal_u = json.loads((root / "int005_capped_us.json").read_text())
    hold_i = json.loads((root / "int005_capped_holdout_india.json").read_text())
    hold_u = json.loads((root / "int005_holdout_us.json").read_text())
    match = json.loads((root / "capped_match_evaluation.json").read_text())
    result = analyze(cal_i, cal_u, hold_i, hold_u, match["error_budget"])
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
