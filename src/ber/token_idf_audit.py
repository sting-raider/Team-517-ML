"""Full Source-1 token DF/IDF forensic audit for F007a.

Reads challenge Source-1 TSV only and emits aggregate statistics. It mirrors the
blocker's lexical token definitions for name-word and address-word channels.
No labels, target-source records, or external data are used.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ADDRESS_STOP = {
    "road", "street", "avenue", "drive", "lane", "floor", "near",
    "opposite", "the", "and", "unit", "plot", "no",
}
DIGIT_RE = re.compile(r"\d+")
THRESHOLDS = (10, 100, 1000)


def normalize(text: str) -> str:
    # Python approximation to DuckDB strip_accents + Unicode letter/digit.
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()
    out = []
    last_space = True
    for ch in text:
        cat = unicodedata.category(ch)
        if cat and cat[0] in ("L", "N"):
            out.append(ch)
            last_space = False
        elif not last_space:
            out.append(" ")
            last_space = True
    return "".join(out).strip()


def name_tokens(name: str) -> set[str]:
    return {t for t in normalize(name).split() if len(t) >= 3}


def address_words(address: str) -> set[str]:
    return {
        t for t in normalize(address).split()
        if len(t) >= 3 and not t.isdigit() and t not in ADDRESS_STOP
    }


def qtile(vals: list[int], q: float) -> int | None:
    if not vals:
        return None
    i = min(len(vals) - 1, max(0, math.ceil(q * len(vals)) - 1))
    return vals[i]


def df_summary(counter: Counter[str]) -> dict:
    vals = sorted(counter.values())
    postings = sum(vals)
    vocab = len(vals)
    eligible_vocab = sum(v <= 1000 for v in vals)
    eligible_postings = sum(v for v in vals if v <= 1000)
    return {
        "vocab": vocab,
        "posting_mass": postings,
        "vocab_df_le_1000_rate": eligible_vocab / vocab if vocab else 0.0,
        "posting_mass_df_le_1000_rate": eligible_postings / postings if postings else 0.0,
        "df_quantiles": {
            "min": vals[0] if vals else None,
            "p25": qtile(vals, .25),
            "p50": qtile(vals, .50),
            "p75": qtile(vals, .75),
            "p90": qtile(vals, .90),
            "p95": qtile(vals, .95),
            "p99": qtile(vals, .99),
            "max": vals[-1] if vals else None,
        },
    }


def update_coverage(acc: Counter, toks: set[str], df: Counter[str], max_probes: int) -> None:
    acc["records"] += 1
    if not toks:
        acc["no_tokens"] += 1
        return
    if len(toks) > max_probes:
        acc["raw_token_count_gt_probe"] += 1
    for threshold in THRESHOLDS:
        if any(df[x] <= threshold for x in toks):
            acc[f"any_df_le_{threshold}"] += 1
    eligible = sorted((df[x], x) for x in toks if df[x] <= 1000)
    if not eligible:
        acc["all_tokens_df_gt_1000"] += 1
        return
    acc["selected_records"] += 1
    acc["eligible_keys"] += len(eligible)
    selected = eligible[:max_probes]
    acc["selected_keys"] += len(selected)
    acc["selected_df_sum"] += sum(v for v, _ in selected)


def finish_coverage(acc: Counter) -> dict:
    n = acc["records"]
    eligible = acc["eligible_keys"]
    selected = acc["selected_keys"]
    dropped = eligible - selected
    return {
        "records": n,
        "no_tokens": acc["no_tokens"],
        "raw_token_count_gt_probe": acc["raw_token_count_gt_probe"],
        "raw_token_count_gt_probe_rate": acc["raw_token_count_gt_probe"] / n if n else 0.0,
        **{f"any_df_le_{t}_rate": acc[f"any_df_le_{t}"] / n if n else 0.0 for t in THRESHOLDS},
        "all_tokens_df_gt_1000": acc["all_tokens_df_gt_1000"],
        "all_tokens_df_gt_1000_rate": acc["all_tokens_df_gt_1000"] / n if n else 0.0,
        "eligible_df_le_1000_query_keys": eligible,
        "selected_query_keys": selected,
        "dropped_by_probe_limit": dropped,
        "dropped_by_probe_limit_rate": dropped / eligible if eligible else 0.0,
        "selected_records": acc["selected_records"],
        "mean_selected_df_sum": (
            acc["selected_df_sum"] / acc["selected_records"]
            if acc["selected_records"] else 0.0
        ),
    }


def audit(path: Path, max_probes: int = 4) -> dict:
    started = time.time()
    counters = defaultdict(
        lambda: {"name": Counter(), "address": Counter(), "digit": Counter()}
    )
    meta = defaultdict(Counter)

    # Pass 1: country-local document frequencies and structural census.
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            country = row.get("country", "")
            name = row.get("business_name", "") or ""
            addr = row.get("business_address", "") or ""
            nt = name_tokens(name)
            aw = address_words(addr)
            digits = set(DIGIT_RE.findall(normalize(addr)))
            counters[country]["name"].update(nt)
            counters[country]["address"].update(aw)
            counters[country]["digit"].update(digits)
            m = meta[country]
            m["records"] += 1
            m["empty_name"] += not bool(name)
            m["empty_address"] += not bool(addr)
            m["non_ascii_name"] += any(ord(c) > 127 for c in name)
            m["non_ascii_address"] += any(ord(c) > 127 for c in addr)
            m["has_digit"] += bool(digits)
            m[f"name_tok_count_{min(len(nt), 20)}"] += 1
            m[f"address_word_count_{min(len(aw), 20)}"] += 1

    # Pass 2: per-record coverage under the current DF cutoff / probe count.
    coverage = defaultdict(lambda: {"name": Counter(), "address": Counter()})
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            country = row.get("country", "")
            update_coverage(
                coverage[country]["name"],
                name_tokens(row.get("business_name", "") or ""),
                counters[country]["name"],
                max_probes,
            )
            update_coverage(
                coverage[country]["address"],
                address_words(row.get("business_address", "") or ""),
                counters[country]["address"],
                max_probes,
            )

    out = {"source": str(path), "max_probes": max_probes, "df_cutoff": 1000, "countries": {}}
    for country in sorted(counters):
        n = meta[country]["records"]
        out["countries"][country] = {
            "meta": {
                "records": n,
                "empty_name": meta[country]["empty_name"],
                "empty_address": meta[country]["empty_address"],
                "non_ascii_name": meta[country]["non_ascii_name"],
                "non_ascii_address": meta[country]["non_ascii_address"],
                "digit_address_coverage_rate": meta[country]["has_digit"] / n if n else 0.0,
                "name_token_count_distribution": {
                    k.removeprefix("name_tok_count_"): v
                    for k, v in sorted(meta[country].items())
                    if k.startswith("name_tok_count_")
                },
                "address_word_count_distribution": {
                    k.removeprefix("address_word_count_"): v
                    for k, v in sorted(meta[country].items())
                    if k.startswith("address_word_count_")
                },
            },
            "name": {
                **df_summary(counters[country]["name"]),
                **finish_coverage(coverage[country]["name"]),
            },
            "address": {
                **df_summary(counters[country]["address"]),
                **finish_coverage(coverage[country]["address"]),
            },
            "digit": df_summary(counters[country]["digit"]),
        }
    out["runtime_seconds"] = time.time() - started
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source1", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-probes", type=int, default=4)
    args = p.parse_args()
    if args.max_probes <= 0:
        raise ValueError("--max-probes must be positive")
    result = audit(args.source1, args.max_probes)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
