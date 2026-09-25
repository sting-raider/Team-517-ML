#!/usr/bin/env python3
"""Deterministic audit of blocker-v2 correlated retrieval-key score inflation.

This mirrors the score formula in src/ber/blocking.py without requiring DuckDB or
challenge records. It is intentionally a Tier-0/1 diagnostic, not an end-to-end
retrieval benchmark.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

IDF_NUMERATOR = 10_000_001.0
BONUS = {"n:": 50.0, "a:": 40.0, "w:": 0.0}


def contribution(kind: str, freq: int) -> float:
    if freq < 1 or freq > 1000:
        raise ValueError("freq must be within blocker-v2 eligible range [1, 1000]")
    return BONUS.get(kind, 8.0) + math.log(IDF_NUMERATOR / freq)


def address_stack_keys(eligible_words: int, freq: int = 1000, include_h: bool = True):
    if eligible_words < 1:
        raise ValueError("eligible_words must be >= 1")
    m = min(eligible_words, 4)
    keys = [("a:", freq)]
    keys += [("u:", freq)] * m
    keys += [("v:", freq)] * min(max(eligible_words - 1, 0), 4)
    keys += [("d:", freq)] * m
    if include_h:
        keys += [("h:", freq)]
    return keys


def score_sum(keys) -> float:
    return sum(contribution(kind, freq) for kind, freq in keys)


def evidence_family(kind: str) -> str:
    if kind == "n:":
        return "name_exact"
    if kind == "w:":
        return "name_lexical"
    if kind == "a:":
        return "address_exact"
    if kind in {"u:", "v:"}:
        return "address_lexical"
    if kind in {"d:", "h:", "z:"}:
        return "number_composite"
    return kind


def score_family_max(keys) -> float:
    """Illustrative decorrelated score: max contribution per evidence super-family.

    This is not a production recommendation without a paired full-data benchmark.
    """
    best = defaultdict(lambda: float("-inf"))
    for kind, freq in keys:
        family = evidence_family(kind)
        best[family] = max(best[family], contribution(kind, freq))
    return sum(best.values())


def audit() -> dict:
    rare_name_keys = [("w:", 1)] * 4
    rare_name_score = score_sum(rare_name_keys)
    rows = []
    for words in (1, 2, 3, 4):
        keys = address_stack_keys(words, freq=1000, include_h=True)
        current = score_sum(keys)
        family_max = score_family_max(keys)
        exact_address = contribution("a:", 1000)
        rows.append({
            "eligible_address_words": words,
            "derived_hit_count": len(keys),
            "current_sum_score": current,
            "exact_address_only_score": exact_address,
            "inflation_vs_exact_address": current / exact_address,
            "family_max_score": family_max,
            "current_vs_family_max_ratio": current / family_max,
            "four_maximally_rare_name_words_score": rare_name_score,
            "address_stack_outranks_four_rare_name_words": current > rare_name_score,
        })
    return {
        "formula": "bonus(kind) + ln(10000001/freq), summed across shared keys",
        "max_eligible_frequency": 1000,
        "rare_name_reference_score": rare_name_score,
        "scenarios": rows,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    result = audit()
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
