"""Audit candidate-budget/quality tradeoffs from committed calibration artifacts.

This helper intentionally consumes only aggregate repository reports. It does not
read challenge rows or tune against confirmation/frozen holdouts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CANDIDATE_METRICS = (
    "entities",
    "singleton_count",
    "all_empty_baseline",
    "candidate_pair_recall",
    "candidate_entity_recall",
    "all_matches_retrieved_rate",
    "blocking_oracle_macro_f0_5",
    "candidate_count_quantiles",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _test_anchor_count(data_audit: dict[str, Any]) -> int:
    rows = [r for r in data_audit["test"] if int(r["source"]) == 1]
    if not rows:
        raise ValueError("data_audit has no test Source-1 rows")
    return sum(int(r["records"]) for r in rows)


def _assert_same_candidate_semantics(
    wide: dict[str, Any], retrieval: dict[str, Any], tol: float = 1e-12
) -> None:
    common = sorted(set(wide) & set(retrieval))
    if not common:
        raise ValueError("wide_calibration and retrieval_study share no configurations")
    for key in common:
        for metric in CANDIDATE_METRICS:
            a = wide[key][metric]
            b = retrieval[key][metric]
            if isinstance(a, dict):
                if a != b:
                    raise ValueError(f"{key}: {metric} mismatch: {a!r} != {b!r}")
            elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if abs(float(a) - float(b)) > tol:
                    raise ValueError(f"{key}: {metric} mismatch: {a!r} != {b!r}")
            elif a != b:
                raise ValueError(f"{key}: {metric} mismatch: {a!r} != {b!r}")


def _rows(wide: dict[str, Any], test_anchors: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, stats in wide.items():
        if "_" not in key:
            continue
        mode, cap_text = key.rsplit("_", 1)
        try:
            cap = int(cap_text)
        except ValueError:
            continue
        q = stats["candidate_count_quantiles"]
        rows.append({
            "config": key,
            "mode": mode,
            "cap": cap,
            "macro_f0_5": float(stats["macro_f0_5"]),
            "candidate_pair_recall": float(stats["candidate_pair_recall"]),
            "candidate_entity_recall": float(stats["candidate_entity_recall"]),
            "all_matches_retrieved_rate": float(stats["all_matches_retrieved_rate"]),
            "blocking_oracle_macro_f0_5": float(stats["blocking_oracle_macro_f0_5"]),
            "singleton_false_positive_rate": float(stats["singleton_false_positive_rate"]),
            "p50_candidates": float(q["p50"]),
            "p90_candidates": float(q["p90"]),
            "p99_candidates": float(q["p99"]),
            "max_candidates": float(q["max"]),
            "matcher_gap_to_oracle": float(
                stats["blocking_oracle_macro_f0_5"] - stats["macro_f0_5"]
            ),
            "test_candidate_entries_upper_bound": int(cap * test_anchors),
            "test_p50_equivalent_entries": int(round(float(q["p50"]) * test_anchors)),
        })
    return sorted(rows, key=lambda r: (r["mode"], r["cap"]))


def _annotate_marginals(rows: list[dict[str, Any]]) -> None:
    for mode in sorted({r["mode"] for r in rows}):
        prev = None
        for row in [r for r in rows if r["mode"] == mode]:
            if prev is not None:
                added_p50 = row["p50_candidates"] - prev["p50_candidates"]
                row["marginal_vs_previous_cap"] = {
                    "delta_macro_f0_5": row["macro_f0_5"] - prev["macro_f0_5"],
                    "delta_candidate_pair_recall": (
                        row["candidate_pair_recall"] - prev["candidate_pair_recall"]
                    ),
                    "delta_blocking_oracle_macro_f0_5": (
                        row["blocking_oracle_macro_f0_5"]
                        - prev["blocking_oracle_macro_f0_5"]
                    ),
                    "delta_singleton_false_positive_rate": (
                        row["singleton_false_positive_rate"]
                        - prev["singleton_false_positive_rate"]
                    ),
                    "added_p50_candidates": added_p50,
                    "macro_f0_5_gain_per_100_added_p50_candidates": (
                        100.0
                        * (row["macro_f0_5"] - prev["macro_f0_5"])
                        / added_p50
                        if added_p50 > 0
                        else None
                    ),
                }
            prev = row


def _annotate_pareto(rows: list[dict[str, Any]]) -> None:
    """Pareto dominance: macro F0.5 higher/equal and median candidates lower/equal."""
    for row in rows:
        dominated_by = []
        for other in rows:
            if other is row:
                continue
            no_worse = (
                other["macro_f0_5"] >= row["macro_f0_5"]
                and other["p50_candidates"] <= row["p50_candidates"]
            )
            strict = (
                other["macro_f0_5"] > row["macro_f0_5"]
                or other["p50_candidates"] < row["p50_candidates"]
            )
            if no_worse and strict:
                dominated_by.append(other["config"])
        row["dominated_by"] = sorted(dominated_by)
        row["pareto_efficient"] = not dominated_by


def build_report(root: Path) -> dict[str, Any]:
    reports = root / "reports"
    wide = _load(reports / "wide_calibration.json")
    retrieval = _load(reports / "retrieval_study.json")
    tuning = _load(reports / "tuning.json")
    data_audit = _load(reports / "data_audit.json")
    _assert_same_candidate_semantics(wide, retrieval)
    test_anchors = _test_anchor_count(data_audit)
    rows = _rows(wide, test_anchors)
    _annotate_marginals(rows)
    _annotate_pareto(rows)

    by_key = {r["config"]: r for r in rows}
    lex80 = by_key.get("lexical_80")
    lex640 = by_key.get("lexical_640")
    depth10 = tuning.get("depth10")
    if lex80 is None or lex640 is None or depth10 is None:
        raise ValueError("required lexical_80/lexical_640/depth10 artifacts are missing")

    summary = {
        "calibration_entities": int(wide["retrieval_80"]["entities"]),
        "test_source1_anchors": test_anchors,
        "lexical_80_to_640": {
            "delta_macro_f0_5_initial_classifier": (
                lex640["macro_f0_5"] - lex80["macro_f0_5"]
            ),
            "delta_candidate_pair_recall": (
                lex640["candidate_pair_recall"] - lex80["candidate_pair_recall"]
            ),
            "delta_blocking_oracle_macro_f0_5": (
                lex640["blocking_oracle_macro_f0_5"]
                - lex80["blocking_oracle_macro_f0_5"]
            ),
            "delta_singleton_false_positive_rate": (
                lex640["singleton_false_positive_rate"]
                - lex80["singleton_false_positive_rate"]
            ),
            "p50_candidate_ratio": (
                lex640["p50_candidates"] / lex80["p50_candidates"]
            ),
            "cap_ratio": lex640["cap"] / lex80["cap"],
            "macro_f0_5_gain_per_100_added_p50_candidates": (
                100.0
                * (lex640["macro_f0_5"] - lex80["macro_f0_5"])
                / (lex640["p50_candidates"] - lex80["p50_candidates"])
            ),
        },
        "selected_depth10_640": {
            "macro_f0_5": float(depth10["macro_f0_5"]),
            "threshold": float(depth10["threshold"]),
            "candidate_cap": int(depth10["candidate_count_quantiles"]["max"]),
            "same_model_smaller_cap_sweep_available": False,
            "reason": "tuning.json records depth10 only on the 640-candidate wide pool",
        },
        "interpretation_guardrail": (
            "The Pareto rows use the address_baseline classifier from "
            "wide_calibration.json. They do not establish the selected depth10 "
            "model's score at smaller caps."
        ),
    }
    return {"summary": summary, "configs": rows}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    report = build_report(args.repo_root)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
