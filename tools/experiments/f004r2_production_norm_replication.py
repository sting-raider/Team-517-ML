#!/usr/bin/env python3
"""F004R2: full Source-1 replication of same-address collisions under production-normalization semantics.

This helper is deliberately Source-1 only. It does not use entity IDs as evidence,
ground truth, S2/S3 records, confirmation windows, or external identity data.

DuckDB 1.5.5 implements strip_accents with vendored utf8proc as:
  utf8proc_map(..., UTF8PROC_STABLE | UTF8PROC_COMPOSE | UTF8PROC_STRIPMARK)
For the observed Source-1 non-ASCII codepoint domain, the Python emulation below
(canonical decomposition, remove Unicode marks, canonical composition) is equivalent.
The helper audits that production-semantics emulation against F004's prior NFD/Mn
fallback on every non-ASCII address row before reusing the full-data collision census.
It must not be treated as a general DuckDB replacement for arbitrary unseen Unicode.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import resource
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


_ASCII_SEP = re.compile(r"[^a-z0-9]+")


def f004_fallback_norm(value: str | None) -> str:
    value = value or ""
    if value.isascii():
        return _ASCII_SEP.sub(" ", value.lower()).strip()
    value = value.lower()
    value = "".join(
        ch
        for ch in unicodedata.normalize("NFD", value)
        if unicodedata.category(ch) != "Mn"
    )
    return _collapse_non_alnum(value)


def utf8proc_stripmark_emulation(value: str | None) -> str:
    """Emulate utf8proc COMPOSE|STRIPMARK for the audited codepoint domain."""
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(
        ch for ch in value if not unicodedata.category(ch).startswith("M")
    )
    return unicodedata.normalize("NFC", value)


def production_norm_emulation(value: str | None) -> str:
    # latest-main data.py: lower(strip_accents(coalesce(...))) then replace non L/N
    return _collapse_non_alnum(utf8proc_stripmark_emulation(value).lower())


def _collapse_non_alnum(value: str) -> str:
    out: list[str] = []
    previous_separator = True
    for ch in value:
        category = unicodedata.category(ch)
        if category and category[0] in {"L", "N"}:
            out.append(ch)
            previous_separator = False
        elif not previous_separator:
            out.append(" ")
            previous_separator = True
    return "".join(out).strip()


def choose2(n: int) -> int:
    return n * (n - 1) // 2


def nearest_rank(values: list[int], p: float) -> int | None:
    if not values:
        return None
    values = sorted(values)
    return values[max(0, min(len(values) - 1, math.ceil(p * len(values)) - 1))]


def _final_group_stats(
    country: str,
    records: int,
    groups: dict[tuple[str, str], Counter[str]],
    nonascii_collision_rows: Counter[tuple[str, str]],
) -> dict:
    selected = [
        (key, name_counts)
        for key, name_counts in groups.items()
        if country == "ALL" or key[0] == country
    ]
    collision_records = 0
    collision_pairs = 0
    same_name_pairs = 0
    cross_name_pairs = 0
    shared_token_pairs = 0
    jaccard_gt_025_pairs = 0
    compact_prefix6_pairs = 0
    group_sizes: list[int] = []
    hard_groups = 0
    hard_groups_ge6 = 0
    pair_mass_ge6 = 0

    for (_, _address), names in selected:
        n = sum(names.values())
        group_sizes.append(n)
        collision_records += n
        all_pairs = choose2(n)
        collision_pairs += all_pairs
        same = sum(choose2(count) for count in names.values())
        same_name_pairs += same
        cross = all_pairs - same
        cross_name_pairs += cross
        if len(names) <= 1:
            continue
        hard_groups += 1
        if n >= 6:
            hard_groups_ge6 += 1
            pair_mass_ge6 += cross
        items = list(names.items())
        for i, (left, left_count) in enumerate(items):
            left_tokens = set(left.split())
            left_compact = left.replace(" ", "")
            for right, right_count in items[i + 1 :]:
                weight = left_count * right_count
                right_tokens = set(right.split())
                inter = len(left_tokens & right_tokens)
                union = len(left_tokens | right_tokens)
                if inter:
                    shared_token_pairs += weight
                if (inter / union if union else 0.0) > 0.25:
                    jaccard_gt_025_pairs += weight
                right_compact = right.replace(" ", "")
                if left_compact[:6] and left_compact[:6] == right_compact[:6]:
                    compact_prefix6_pairs += weight

    return {
        "records": records,
        "collision_groups": len(selected),
        "collision_records": collision_records,
        "collision_record_rate": collision_records / records if records else None,
        "collision_pairs": collision_pairs,
        "same_name_pairs": same_name_pairs,
        "cross_name_pairs": cross_name_pairs,
        "hard_negative_like_groups": hard_groups,
        "shared_name_token_pairs": shared_token_pairs,
        "shared_name_token_rate": (
            shared_token_pairs / cross_name_pairs if cross_name_pairs else None
        ),
        "name_jaccard_gt_0_25_pairs": jaccard_gt_025_pairs,
        "name_jaccard_gt_0_25_rate": (
            jaccard_gt_025_pairs / cross_name_pairs if cross_name_pairs else None
        ),
        "compact_prefix6_equal_pairs": compact_prefix6_pairs,
        "compact_prefix6_equal_rate": (
            compact_prefix6_pairs / cross_name_pairs if cross_name_pairs else None
        ),
        "groups_ge6_rate": hard_groups_ge6 / hard_groups if hard_groups else None,
        "pair_mass_ge6_rate": (
            pair_mass_ge6 / cross_name_pairs if cross_name_pairs else None
        ),
        "group_size_quantiles": {
            "p50": nearest_rank(group_sizes, 0.50),
            "p90": nearest_rank(group_sizes, 0.90),
            "p99": nearest_rank(group_sizes, 0.99),
            "max": max(group_sizes) if group_sizes else None,
        },
        "nonascii_collision_rows": sum(
            count
            for key, count in nonascii_collision_rows.items()
            if country == "ALL" or key[0] == country
        ),
    }


def audit(input_path: Path) -> dict:
    started = time.time()
    address_counts: Counter[tuple[str, str]] = Counter()
    country_records: Counter[str] = Counter()
    empty_addresses: Counter[str] = Counter()
    nonascii_rows = 0
    nonascii_codepoints: Counter[str] = Counter()
    parity_mismatches: list[dict[str, str]] = []

    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"business_name", "business_address", "country"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        for row in reader:
            country = row["country"]
            address = row.get("business_address") or ""
            country_records[country] += 1
            if any(ord(ch) > 127 for ch in address):
                nonascii_rows += 1
                for ch in set(address):
                    if ord(ch) > 127:
                        nonascii_codepoints[
                            f"U+{ord(ch):04X} {unicodedata.name(ch, '<unnamed>')}"
                        ] += 1
                fallback = f004_fallback_norm(address)
                production = production_norm_emulation(address)
                if fallback != production and len(parity_mismatches) < 20:
                    parity_mismatches.append(
                        {
                            "country": country,
                            "fallback": fallback,
                            "production": production,
                        }
                    )
            normalized = f004_fallback_norm(address)
            if not normalized:
                empty_addresses[country] += 1
            else:
                address_counts[(country, normalized)] += 1

    collision_counts = {
        key: count for key, count in address_counts.items() if count >= 2
    }
    collision_names: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    nonascii_collision_rows: Counter[tuple[str, str]] = Counter()

    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            country = row["country"]
            address = row.get("business_address") or ""
            key = (country, f004_fallback_norm(address))
            if key not in collision_counts:
                continue
            collision_names[key][f004_fallback_norm(row.get("business_name") or "")] += 1
            if any(ord(ch) > 127 for ch in address):
                nonascii_collision_rows[key] += 1

    countries = sorted(country_records)
    metrics = {
        country: _final_group_stats(
            country,
            country_records[country],
            collision_names,
            nonascii_collision_rows,
        )
        for country in countries
    }
    metrics["ALL"] = _final_group_stats(
        "ALL",
        sum(country_records.values()),
        collision_names,
        nonascii_collision_rows,
    )

    elapsed = time.time() - started
    return {
        "experiment_id": "F004R2",
        "protocol": {
            "input": str(input_path),
            "rows": sum(country_records.values()),
            "countries": dict(country_records),
            "passes": 2,
            "entity_id_used_as_evidence": False,
            "ground_truth_used": False,
            "s2_s3_used": False,
            "normalization_reference": (
                "DuckDB 1.5.5 utf8proc STABLE|COMPOSE|STRIPMARK; "
                "latest-main lower + Unicode L/N separator collapse"
            ),
        },
        "normalization_parity": {
            "nonascii_address_rows": nonascii_rows,
            "observed_nonascii_codepoints": dict(nonascii_codepoints),
            "fallback_vs_production_semantics_mismatches": len(parity_mismatches),
            "mismatch_examples": parity_mismatches,
            "scope_note": (
                "Parity claim is corpus-domain-specific; this helper is not a "
                "general substitute for DuckDB strip_accents on arbitrary Unicode."
            ),
        },
        "metrics": metrics,
        "runtime": {
            "wall_seconds": elapsed,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
