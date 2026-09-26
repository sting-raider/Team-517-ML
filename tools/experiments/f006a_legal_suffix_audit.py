#!/usr/bin/env python3
"""Full Source-1 legal-form suffix collision audit for F006a.

Uses only supplied Source-1 TSVs. It mirrors the repository normalization
semantics (accent stripping, lowercase, non-letter/number -> spaces) with
Python stdlib so it can run without DuckDB.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import time
import unicodedata
from pathlib import Path

COMPOUND = [
    (("private", "limited"), "private limited"),
    (("pvt", "ltd"), "pvt ltd"),
    (("public", "limited"), "public limited"),
    (("p", "c"), "p c"),
    (("l", "c"), "l c"),
]
SINGLE = {
    "limited": "limited", "ltd": "ltd", "llc": "llc", "inc": "inc",
    "corp": "corp", "corporation": "corporation", "company": "company",
    "co": "co", "llp": "llp", "lp": "lp", "pllc": "pllc", "pc": "pc",
    "sarl": "sarl", "sas": "sas", "eurl": "eurl", "sa": "sa",
    "sasu": "sasu", "sci": "sci", "ei": "ei",
}
BUNDLES = {
    "US_major2": {"llc", "inc"},
    "US_core": {"llc", "inc", "corp", "corporation", "co", "company",
                "llp", "lp", "pllc", "pc", "p c", "l c"},
    "India_major2": {"private limited", "pvt ltd"},
    "India_core": {"private limited", "pvt ltd", "public limited", "limited",
                   "ltd", "llp", "co", "company", "corp", "corporation"},
    "France_major2": {"sarl", "sas"},
    "France_core": {"sarl", "sas", "eurl", "sa", "sasu", "sci", "ei"},
}
SOLO_MAJOR = {
    "US": ("llc", "inc"),
    "India": ("private limited", "pvt ltd"),
    "France": ("sarl", "sas"),
}


def repo_norm(value: str | None) -> str:
    s = "" if value is None else str(value)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    out = []
    pending_space = False
    for ch in s:
        if ch.isalpha() or ch.isdigit():
            if pending_space and out:
                out.append(" ")
            out.append(ch)
            pending_space = False
        else:
            pending_space = True
    return "".join(out).strip()


def strip_suffix(norm: str, selected: set[str] | None = None) -> tuple[str, str]:
    if not norm:
        return norm, ""
    selected = selected if selected is not None else set(SINGLE.values()) | {x[1] for x in COMPOUND}
    toks = norm.split()
    for seq, label in COMPOUND:
        if label in selected and len(toks) > len(seq) and tuple(toks[-len(seq):]) == seq:
            return " ".join(toks[:-len(seq)]), label
    if len(toks) > 1 and toks[-1] in SINGLE and SINGLE[toks[-1]] in selected:
        return " ".join(toks[:-1]), SINGLE[toks[-1]]
    return norm, ""


def load_counters(path: Path) -> tuple[dict[str, collections.Counter], dict[str, int]]:
    by_country: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    totals: dict[str, int] = collections.Counter()
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            country = row.get("country") or ""
            name = repo_norm(row.get("business_name"))
            by_country[country][name] += 1
            totals[country] += 1
    return by_country, totals


def weighted_quantile(hist: collections.Counter, q: float) -> int:
    if not hist:
        return 0
    target = q * sum(hist.values())
    acc = 0
    for value, weight in sorted(hist.items()):
        acc += weight
        if acc >= target:
            return int(value)
    return int(max(hist))


def summarize(counter: collections.Counter, selected: set[str] | None = None) -> dict:
    total = sum(counter.values())
    stripped = collections.Counter()
    distinct_orig = collections.Counter()
    mappings = []
    family_rows = collections.Counter()

    for orig, count in counter.items():
        base, family = strip_suffix(orig, selected)
        stripped[base] += count
        distinct_orig[base] += 1
        if family:
            mappings.append((orig, count, base, family))
            family_rows[family] += count

    affected = sum(x[1] for x in mappings)
    collision_rows = sum(count for _, count, base, _ in mappings if distinct_orig[base] > 1)
    orig_dup_rows = sum(count for count in counter.values() if count > 1)
    after_dup_rows = sum(count for count in stripped.values() if count > 1)

    added_hist = collections.Counter()
    for orig, count, base, _ in mappings:
        added_hist[max(0, stripped[base] - counter[orig])] += count

    return {
        "rows": total,
        "unique_original_norm_names": len(counter),
        "unique_stripped_keys": len(stripped),
        "unique_key_retention": len(stripped) / len(counter) if counter else 1.0,
        "affected_rows": affected,
        "coverage": affected / total if total else 0.0,
        "collision_exposed_rows": collision_rows,
        "collision_rate": collision_rows / affected if affected else 0.0,
        "original_duplicate_row_rate": orig_dup_rows / total if total else 0.0,
        "after_duplicate_row_rate": after_dup_rows / total if total else 0.0,
        "max_fanout": max(stripped.values()) if stripped else 0,
        "keys_gt100": sum(1 for v in stripped.values() if v > 100),
        "rows_gt100": sum(v for v in stripped.values() if v > 100),
        "keys_gt1000": sum(1 for v in stripped.values() if v > 1000),
        "rows_gt1000": sum(v for v in stripped.values() if v > 1000),
        "mean_added_fanout": (
            sum(value * weight for value, weight in added_hist.items()) / affected
            if affected else 0.0
        ),
        "p50_added_fanout": weighted_quantile(added_hist, 0.50),
        "p90_added_fanout": weighted_quantile(added_hist, 0.90),
        "p95_added_fanout": weighted_quantile(added_hist, 0.95),
        "p99_added_fanout": weighted_quantile(added_hist, 0.99),
        "family_rows": dict(family_rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-source1", type=Path, required=True)
    ap.add_argument("--test-source1", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    started = time.perf_counter()
    train, train_totals = load_counters(args.train_source1)
    test, test_totals = load_counters(args.test_source1)
    load_seconds = time.perf_counter() - started

    result = {
        "experiment_id": "F006a",
        "protocol": {
            "train_source1": str(args.train_source1),
            "test_source1": str(args.test_source1),
            "train_rows": sum(train_totals.values()),
            "test_rows": sum(test_totals.values()),
            "suffixes": {
                "compound": [label for _, label in COMPOUND],
                "single": sorted(set(SINGLE.values())),
            },
        },
        "headline": {},
        "bundles": {},
        "solo_major_suffixes": {},
        "timing": {"load_normalize_counter_seconds": load_seconds},
    }

    for split, tables in (("train", train), ("test", test)):
        for country, counter in tables.items():
            key = f"{split}:{country}"
            result["headline"][key] = summarize(counter)

            for bundle_name, selected in BUNDLES.items():
                if bundle_name.startswith(country):
                    result["bundles"][f"{key}:{bundle_name}"] = summarize(counter, selected)

            for suffix in SOLO_MAJOR.get(country, ()):
                result["solo_major_suffixes"][f"{key}:{suffix}"] = summarize(counter, {suffix})

    result["timing"]["total_seconds"] = time.perf_counter() - started
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
