#!/usr/bin/env python3
"""X014: Unicode-preserving decomposition of the R029 France rare-word gate.

Uses only supplied Source-1 records. The four views differ in whether legal-suffix-
stripped business names and selected rare address words use the current folded
normalization or a Unicode-preserving normalization. This is a Source-1
selectivity/collision proxy only, not a target-side recall/F0.5 experiment.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import tempfile
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
SINGLE = {x: x for x in (
    "limited", "ltd", "llc", "inc", "corp", "corporation", "company", "co",
    "llp", "lp", "pllc", "pc", "sarl", "sas", "eurl", "sa", "sasu", "sci", "ei",
)}
ADDRESS_STOP = {
    "road", "street", "avenue", "drive", "lane", "floor", "near",
    "opposite", "the", "and", "unit", "plot", "no",
}
DF_CUTOFF = 1000
SEP_RE = re.compile(r"[\W_]+", re.UNICODE)
R029_EXPECTED = {
    "US": {"coverage": 0.943359, "collision": 0.0008535163182179256},
    "India": {"coverage": 0.932892, "collision": 0.0005596243600082372},
    "France": {"coverage": 0.974058, "collision": 0.018576473628298257},
}


def norm_folded(value: str | None) -> str:
    s = "" if value is None else str(value)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return SEP_RE.sub(" ", s).strip()


def norm_unicode(value: str | None) -> str:
    s = "" if value is None else str(value)
    return SEP_RE.sub(" ", unicodedata.normalize("NFC", s).lower()).strip()


def strip_suffix(norm: str) -> tuple[str, str]:
    if not norm:
        return norm, ""
    toks = norm.split()
    for seq, label in COMPOUND:
        if len(toks) > len(seq) and tuple(toks[-len(seq):]) == seq:
            return " ".join(toks[:-len(seq)]), label
    if len(toks) > 1 and toks[-1] in SINGLE:
        return " ".join(toks[:-1]), SINGLE[toks[-1]]
    return norm, ""


def address_words(addr_norm: str) -> set[str]:
    return {
        t for t in addr_norm.split()
        if len(t) >= 3 and not t.isdigit() and t not in ADDRESS_STOP
    }


def select_rare(words_field: str, df: collections.Counter[str]) -> tuple[str, int | None]:
    if not words_field:
        return "", None
    best = min((df[w], w) for w in words_field.split("\x1e"))
    if best[0] > DF_CUTOFF:
        return "", best[0]
    return best[1], best[0]


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


def preprocess(path: Path, spool: Path, france_spool: Path) -> dict:
    df_fold = collections.defaultdict(collections.Counter)
    df_uni = collections.defaultdict(collections.Counter)
    country_rows = collections.Counter()
    suffix_rows = collections.Counter()
    suffix_mismatch = collections.Counter()
    name_changed = collections.Counter()
    addr_changed = collections.Counter()
    started = time.perf_counter()

    with path.open("r", encoding="utf-8", errors="replace", newline="") as f, \
         spool.open("w", encoding="utf-8", newline="") as out, \
         france_spool.open("w", encoding="utf-8", newline="") as fout:
        rd = csv.DictReader(f, delimiter="\t")
        wr = csv.writer(out, delimiter="\t", lineterminator="\n")
        fwr = csv.writer(fout, delimiter="\t", lineterminator="\n")
        for row in rd:
            country = row.get("country") or ""
            folded_name = norm_folded(row.get("business_name"))
            unicode_name = norm_unicode(row.get("business_name"))
            folded_base, folded_suffix = strip_suffix(folded_name)
            unicode_base, unicode_suffix = strip_suffix(unicode_name)
            folded_addr = norm_folded(row.get("business_address"))
            unicode_addr = norm_unicode(row.get("business_address"))
            folded_words = address_words(folded_addr)
            unicode_words = address_words(unicode_addr)

            df_fold[country].update(folded_words)
            df_uni[country].update(unicode_words)
            country_rows[country] += 1
            suffix_rows[country] += bool(folded_suffix)
            suffix_mismatch[country] += (
                bool(folded_suffix) != bool(unicode_suffix)
                or folded_suffix != unicode_suffix
            )
            name_changed[country] += folded_name != unicode_name
            addr_changed[country] += folded_addr != unicode_addr

            packed = (
                country, folded_name, unicode_name, folded_base, unicode_base,
                "1" if folded_suffix else "0",
                "\x1e".join(sorted(folded_words)),
                "\x1e".join(sorted(unicode_words)),
            )
            wr.writerow(packed)
            if country == "France":
                fwr.writerow(packed)

    return {
        "df_fold": df_fold,
        "df_uni": df_uni,
        "country_rows": country_rows,
        "suffix_rows": suffix_rows,
        "suffix_mismatch": suffix_mismatch,
        "name_changed": name_changed,
        "addr_changed": addr_changed,
        "seconds": time.perf_counter() - started,
    }


def audit_view(
    spool: Path,
    name_mode: str,
    addr_mode: str,
    df_fold: dict[str, collections.Counter[str]],
    df_uni: dict[str, collections.Counter[str]],
    suffix_rows: collections.Counter[str],
) -> tuple[dict, float]:
    groups: dict[str, dict[str, list]] = collections.defaultdict(dict)
    covered = collections.Counter()
    selected_df = collections.defaultdict(collections.Counter)
    changed_key = collections.Counter()
    comparable_key = collections.Counter()
    rare_changed = collections.Counter()
    rare_comparable = collections.Counter()
    started = time.perf_counter()

    with spool.open("r", encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            country, fn, un, fb, ub, suffix_flag, fwf, uwf = row
            base = fb if name_mode == "folded" else ub
            view_orig = fn if name_mode == "folded" else un
            words = fwf if addr_mode == "folded" else uwf
            df = df_fold[country] if addr_mode == "folded" else df_uni[country]
            rare, rare_df = select_rare(words, df)
            key = (base + "\x1f" + rare) if base and rare else None
            is_query = suffix_flag == "1"

            if key is not None:
                g = groups[country].get(key)
                if g is None:
                    groups[country][key] = [1, view_orig, False, un, False, int(is_query)]
                else:
                    g[0] += 1
                    if view_orig != g[1]:
                        g[2] = True
                    if un != g[3]:
                        g[4] = True
                    if is_query:
                        g[5] += 1

            if not is_query:
                continue
            if key is not None:
                covered[country] += 1
                if rare_df is not None:
                    selected_df[country][int(rare_df)] += 1

            baseline_rare, _ = select_rare(fwf, df_fold[country])
            baseline_key = (fb + "\x1f" + baseline_rare) if fb and baseline_rare else None
            if baseline_key is not None and key is not None:
                comparable_key[country] += 1
                changed_key[country] += baseline_key != key
            if baseline_rare and rare:
                rare_comparable[country] += 1
                rare_changed[country] += baseline_rare != rare

    result = {}
    for country, gdict in groups.items():
        collision = strict_collision = 0
        group_hist = collections.Counter()
        for total, _, multi_view, _, multi_unicode, qcount in gdict.values():
            if not qcount:
                continue
            group_hist[total] += qcount
            if multi_view:
                collision += qcount
            if multi_unicode:
                strict_collision += qcount
        cov = covered[country]
        result[country] = {
            "suffix_rows": suffix_rows[country],
            "covered_query_rows": cov,
            "coverage": cov / suffix_rows[country] if suffix_rows[country] else 0.0,
            "cross_original_collision_rows": collision,
            "cross_original_collision_rate": collision / cov if cov else 0.0,
            "unicode_identity_collision_rows": strict_collision,
            "unicode_identity_collision_rate": strict_collision / cov if cov else 0.0,
            "group_size": hist_summary(group_hist),
            "selected_rare_df": hist_summary(selected_df[country]),
            "baseline_key_comparable_rows": comparable_key[country],
            "changed_key_rows_vs_folded_baseline": changed_key[country],
            "changed_key_rate_vs_folded_baseline": (
                changed_key[country] / comparable_key[country]
                if comparable_key[country] else 0.0
            ),
            "rare_token_comparable_rows": rare_comparable[country],
            "rare_token_changed_rows": rare_changed[country],
            "rare_token_changed_rate": (
                rare_changed[country] / rare_comparable[country]
                if rare_comparable[country] else 0.0
            ),
        }
    return result, time.perf_counter() - started


def france_statuses(
    france_spool: Path,
    name_mode: str,
    addr_mode: str,
    df_fold: dict[str, collections.Counter[str]],
    df_uni: dict[str, collections.Counter[str]],
) -> bytearray:
    groups: dict[str, list] = {}
    df = df_fold["France"] if addr_mode == "folded" else df_uni["France"]

    with france_spool.open("r", encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            _, fn, un, fb, ub, _, fwf, uwf = row
            base = fb if name_mode == "folded" else ub
            orig = fn if name_mode == "folded" else un
            words = fwf if addr_mode == "folded" else uwf
            rare, _ = select_rare(words, df)
            if not base or not rare:
                continue
            key = base + "\x1f" + rare
            g = groups.get(key)
            if g is None:
                groups[key] = [orig, False]
            elif orig != g[0]:
                g[1] = True

    status = bytearray()
    with france_spool.open("r", encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            _, _, _, fb, ub, suffix_flag, fwf, uwf = row
            if suffix_flag != "1":
                continue
            base = fb if name_mode == "folded" else ub
            words = fwf if addr_mode == "folded" else uwf
            rare, _ = select_rare(words, df)
            if not base or not rare:
                status.append(0)
            else:
                status.append(2 if groups[base + "\x1f" + rare][1] else 1)
    return status


def transition(a: bytearray, b: bytearray) -> dict[str, int]:
    counts = collections.Counter(zip(a, b))
    return {f"{x}->{y}": n for (x, y), n in sorted(counts.items()) if n}


def run(path: Path) -> dict:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="x014-") as td:
        spool = Path(td) / "all.tsv"
        france_spool = Path(td) / "france.tsv"
        prep = preprocess(path, spool, france_spool)

        configs = {
            "folded_name__folded_rare_word": ("folded", "folded"),
            "folded_name__unicode_rare_word": ("folded", "unicode"),
            "unicode_name__folded_rare_word": ("unicode", "folded"),
            "unicode_name__unicode_rare_word": ("unicode", "unicode"),
        }
        views = {}
        view_seconds = {}
        for label, (nm, am) in configs.items():
            views[label], view_seconds[label] = audit_view(
                spool, nm, am, prep["df_fold"], prep["df_uni"], prep["suffix_rows"]
            )

        statuses = {
            label: france_statuses(
                france_spool, nm, am, prep["df_fold"], prep["df_uni"]
            )
            for label, (nm, am) in configs.items()
        }
        baseline_status = statuses["folded_name__folded_rare_word"]
        paired = {
            label: transition(baseline_status, status)
            for label, status in statuses.items()
            if label != "folded_name__folded_rare_word"
        }

        baseline_fr = views["folded_name__folded_rare_word"]["France"][
            "cross_original_collision_rate"
        ]
        summary = {}
        for label, countries in views.items():
            fr = countries["France"]
            summary[label] = {
                "france_coverage": fr["coverage"],
                "france_collision": fr["cross_original_collision_rate"],
                "collision_delta_pp_vs_baseline": (
                    fr["cross_original_collision_rate"] - baseline_fr
                ) * 100,
                "collision_relative_change": (
                    fr["cross_original_collision_rate"] / baseline_fr - 1
                    if baseline_fr else 0.0
                ),
                "france_group_p99": fr["group_size"]["p99"],
                "france_changed_key_rate_vs_baseline": fr[
                    "changed_key_rate_vs_folded_baseline"
                ],
            }

        parity = {}
        baseline = views["folded_name__folded_rare_word"]
        for country, expected in R029_EXPECTED.items():
            got = baseline[country]
            parity[country] = {
                "coverage_abs_diff_vs_reported_6dp": abs(
                    got["coverage"] - expected["coverage"]
                ),
                "collision_abs_diff": abs(
                    got["cross_original_collision_rate"] - expected["collision"]
                ),
            }
            parity[country]["pass"] = (
                parity[country]["coverage_abs_diff_vs_reported_6dp"] < 5e-7
                and parity[country]["collision_abs_diff"] < 1e-15
            )

        return {
            "experiment_id": "X014",
            "issue": 257,
            "protocol": {
                "file": str(path),
                "bytes": path.stat().st_size,
                "rows": sum(prep["country_rows"].values()),
                "sampling": "none",
                "country_rows": dict(prep["country_rows"]),
                "suffix_rows": dict(prep["suffix_rows"]),
                "df_cutoff": DF_CUTOFF,
                "labels_used": False,
                "target_side_metrics_claimed": False,
                "normalization": {
                    "folded": "NFKD accent removal + lowercase + Unicode alnum separator collapse",
                    "unicode": "NFC + lowercase + Unicode alnum separator collapse, no accent removal",
                },
            },
            "validation": {
                "suffix_set_mismatch": dict(prep["suffix_mismatch"]),
                "fold_change_rates": {
                    c: {
                        "name": prep["name_changed"][c] / prep["country_rows"][c],
                        "address": prep["addr_changed"][c] / prep["country_rows"][c],
                    }
                    for c in prep["country_rows"]
                },
                "r029_exact_parity": parity,
            },
            "views": views,
            "summary": summary,
            "paired_france_status_transitions": paired,
            "runtime_seconds": {
                "preprocess": prep["seconds"],
                "views": view_seconds,
                "total": time.perf_counter() - started,
            },
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-source1", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    result = run(args.test_source1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": result["protocol"]["rows"], "summary": result["summary"]}, indent=2))


if __name__ == "__main__":
    main()
