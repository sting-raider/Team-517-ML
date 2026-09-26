#!/usr/bin/env python3
"""R029: Source-1 feasibility audit for gated legal-suffix-stripped retrieval probes.

Uses only supplied Source-1 TSVs. No labels, IDs-as-evidence, or external data.
The experiment estimates selectivity/collision burden of stripped-name probes when
conjoined with address evidence. Source-1 DF is a feasibility proxy only.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
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
ALL_SUFFIXES = set(SINGLE.values()) | {label for _, label in COMPOUND}
ADDRESS_STOP = {
    "road", "street", "avenue", "drive", "lane", "floor", "near",
    "opposite", "the", "and", "unit", "plot", "no",
}
DIGIT_RE = re.compile(r"\d+")
DF_CUTOFF = 1000
METHODS = ("stripped", "number", "rare_word", "number_rare_word")


def repo_norm(value: str | None) -> str:
    s = "" if value is None else str(value)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    out: list[str] = []
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


def strip_suffix(norm: str) -> tuple[str, str]:
    if not norm:
        return norm, ""
    toks = norm.split()
    for seq, label in COMPOUND:
        if label in ALL_SUFFIXES and len(toks) > len(seq) and tuple(toks[-len(seq):]) == seq:
            return " ".join(toks[:-len(seq)]), label
    if len(toks) > 1 and toks[-1] in SINGLE:
        return " ".join(toks[:-1]), SINGLE[toks[-1]]
    return norm, ""


def address_words_from_norm(addr_norm: str) -> set[str]:
    return {
        t for t in addr_norm.split()
        if len(t) >= 3 and not t.isdigit() and t not in ADDRESS_STOP
    }


def first_number(addr_norm: str) -> str:
    m = DIGIT_RE.search(addr_norm)
    return m.group(0) if m else ""


def choose_rare_word(addr_norm: str, df: collections.Counter[str]) -> tuple[str, int | None]:
    words = address_words_from_norm(addr_norm)
    if not words:
        return "", None
    d, token = min((df[w], w) for w in words)
    if d > DF_CUTOFF:
        return "", d
    return token, d


def weighted_quantile(hist: collections.Counter[int], q: float) -> int:
    if not hist:
        return 0
    target = q * sum(hist.values())
    acc = 0
    for value, weight in sorted(hist.items()):
        acc += weight
        if acc >= target:
            return int(value)
    return int(max(hist))


def hist_summary(hist: collections.Counter[int]) -> dict:
    n = sum(hist.values())
    return {
        "mean": (sum(k * v for k, v in hist.items()) / n) if n else 0.0,
        "p50": weighted_quantile(hist, 0.50),
        "p90": weighted_quantile(hist, 0.90),
        "p95": weighted_quantile(hist, 0.95),
        "p99": weighted_quantile(hist, 0.99),
        "max": max(hist) if hist else 0,
    }


def preprocess(path: Path, spool: Path):
    """One raw-file pass: normalize once, build DFs/frequencies, write temporary normalized rows."""
    name_freq: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    word_df: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    totals: dict[str, int] = collections.Counter()
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f, \
         spool.open("w", encoding="utf-8", newline="") as out:
        w = csv.writer(out, delimiter="\t", lineterminator="\n")
        for row in csv.DictReader(f, delimiter="\t"):
            country = row.get("country") or ""
            orig = repo_norm(row.get("business_name"))
            base, suffix = strip_suffix(orig)
            addr = repo_norm(row.get("business_address"))
            words = address_words_from_norm(addr)
            num = first_number(addr)
            name_freq[country][orig] += 1
            word_df[country].update(words)
            totals[country] += 1
            w.writerow((country, orig, base, "1" if suffix else "0", num, "\x1e".join(sorted(words))))
    return name_freq, word_df, totals


def make_key_spooled(method: str, base: str, num: str, words_field: str,
                     df: collections.Counter[str]) -> tuple[str, int | None] | None:
    if not base:
        return None
    if method == "stripped":
        return base, None
    if method == "number":
        return (base + "\x1f" + num, None) if num else None
    words = words_field.split("\x1e") if words_field else []
    if words:
        rare_df, rare = min((df[w], w) for w in words)
        if rare_df > DF_CUTOFF:
            rare = ""
    else:
        rare_df, rare = None, ""
    if method == "rare_word":
        return (base + "\x1f" + rare, rare_df) if rare else None
    if method == "number_rare_word":
        return (base + "\x1f" + num + "\x1f" + rare, rare_df) if num and rare else None
    raise ValueError(method)


def add_group(groups: dict[str, list], key: str, orig: str, query: bool) -> None:
    # total, first_orig, first_total, others_total_or_none,
    # query_total, first_query, others_query_or_none.
    g = groups.get(key)
    if g is None:
        groups[key] = [1, orig, 1, None, int(query), int(query), None]
        return
    g[0] += 1
    if orig == g[1]:
        g[2] += 1
        if query:
            g[4] += 1
            g[5] += 1
        return
    if g[3] is None:
        g[3] = {}
    g[3][orig] = g[3].get(orig, 0) + 1
    if query:
        g[4] += 1
        if g[6] is None:
            g[6] = {}
        g[6][orig] = g[6].get(orig, 0) + 1


def summarize_groups(groups: dict[str, list], orig_freq: collections.Counter[str], suffix_rows: int,
                     gate_df_hist: collections.Counter[int]) -> dict:
    qrows = duplicate_rows = collision_rows = 0
    group_hist: collections.Counter[int] = collections.Counter()
    added_hist: collections.Counter[int] = collections.Counter()
    cross_orig_hist: collections.Counter[int] = collections.Counter()
    distinct_query_keys = keys_gt10 = keys_gt100 = 0
    for g in groups.values():
        total, first_orig, first_total, others, qtotal, first_q, other_q = g
        if not qtotal:
            continue
        distinct_query_keys += 1
        qrows += qtotal
        group_hist[total] += qtotal
        if total > 1:
            duplicate_rows += qtotal
        if others:
            collision_rows += qtotal
        if total > 10:
            keys_gt10 += 1
        if total > 100:
            keys_gt100 += 1
        if first_q:
            added_hist[max(0, total - orig_freq[first_orig])] += first_q
            cross_orig_hist[total - first_total] += first_q
        if other_q:
            for orig, qcount in other_q.items():
                same_in_group = others.get(orig, 0) if others else 0
                added_hist[max(0, total - orig_freq[orig])] += qcount
                cross_orig_hist[total - same_in_group] += qcount
    out = {
        "suffix_rows": suffix_rows,
        "covered_query_rows": qrows,
        "coverage_among_suffix_rows": qrows / suffix_rows if suffix_rows else 0.0,
        "distinct_query_keys": distinct_query_keys,
        "duplicate_exposed_query_rows": duplicate_rows,
        "duplicate_exposed_rate": duplicate_rows / qrows if qrows else 0.0,
        "cross_original_collision_query_rows": collision_rows,
        "cross_original_collision_rate": collision_rows / qrows if qrows else 0.0,
        "group_size": hist_summary(group_hist),
        "positive_incremental_fanout_vs_original_name": hist_summary(added_hist),
        "cross_original_fanout": hist_summary(cross_orig_hist),
        "query_keys_gt10_rows_group": keys_gt10,
        "query_keys_gt100_rows_group": keys_gt100,
    }
    if gate_df_hist:
        out["selected_rare_word_df"] = hist_summary(gate_df_hist)
        denom = sum(gate_df_hist.values())
        out["selected_rare_word_df_le_10_rate"] = sum(v for k, v in gate_df_hist.items() if k <= 10) / denom
        out["selected_rare_word_df_le_100_rate"] = sum(v for k, v in gate_df_hist.items() if k <= 100) / denom
    return out


def audit_method_spooled(spool: Path, method: str, name_freq: dict[str, collections.Counter[str]],
                         word_df: dict[str, collections.Counter[str]]) -> dict[str, dict]:
    groups: dict[str, dict[str, list]] = collections.defaultdict(dict)
    suffix_rows: dict[str, int] = collections.Counter()
    rare_df_hist: dict[str, collections.Counter[int]] = collections.defaultdict(collections.Counter)
    with spool.open("r", encoding="utf-8", newline="") as f:
        for country, orig, base, suffix_flag, num, words_field in csv.reader(f, delimiter="\t"):
            is_query = suffix_flag == "1"
            if is_query:
                suffix_rows[country] += 1
            result = make_key_spooled(method, base, num, words_field, word_df[country])
            if result is None:
                continue
            key, rare_df = result
            add_group(groups[country], key, orig, is_query)
            if is_query and rare_df is not None:
                rare_df_hist[country][int(rare_df)] += 1
    return {
        country: summarize_groups(groups[country], name_freq[country], suffix_rows[country], rare_df_hist[country])
        for country in name_freq
    }


def audit_file(path: Path) -> dict:
    import tempfile
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="r029-") as td:
        spool = Path(td) / "normalized.tsv"
        name_freq, word_df, totals = preprocess(path, spool)
        base_seconds = time.perf_counter() - started
        print(f"{path.name} preprocess: {base_seconds:.1f}s", flush=True)
        result = {
            "path": str(path),
            "rows": sum(totals.values()),
            "country_rows": dict(totals),
            "address_word_df_cutoff": DF_CUTOFF,
            "methods": {},
            "timing_seconds": {"preprocess": base_seconds},
        }
        for method in METHODS:
            t = time.perf_counter()
            result["methods"][method] = audit_method_spooled(spool, method, name_freq, word_df)
            result["timing_seconds"][method] = time.perf_counter() - t
            print(f"{path.name} {method}: {result['timing_seconds'][method]:.1f}s", flush=True)
        result["timing_seconds"]["total"] = time.perf_counter() - started
        return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-source1", type=Path, required=True)
    ap.add_argument("--test-source1", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    started = time.perf_counter()
    out = {
        "experiment_id": "R029",
        "definition": {
            "suffixes": sorted(ALL_SUFFIXES),
            "address_word_min_length": 3,
            "address_stop": sorted(ADDRESS_STOP),
            "rare_word_df_cutoff": DF_CUTOFF,
            "rare_word_tie_break": "minimum (DF, token) lexicographically",
            "number_gate": "first digit run in normalized address",
            "source1_df_note": "country/split-local Source-1 feasibility proxy; not production S2/S3 posting DF",
        },
        "train": audit_file(args.train_source1),
        "test": audit_file(args.test_source1),
    }
    out["wall_seconds"] = time.perf_counter() - started
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "wall_seconds": out["wall_seconds"],
        "train_rows": out["train"]["rows"],
        "test_rows": out["test"]["rows"],
    }, indent=2))


if __name__ == "__main__":
    main()
