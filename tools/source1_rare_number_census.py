#!/usr/bin/env python3
"""Full Source-1 census of ASCII digit-run prevalence and country-local DF."""
import argparse
import csv
import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

DIGITS = re.compile(r"[0-9]+")
FIELDS = (("name", 1), ("address", 2))
CUTOFFS = (1, 2, 5, 10, 50, 100, 1000)


def _quantile_from_hist(hist, q):
    total = sum(hist.values())
    if not total:
        return None
    rank = max(1, math.ceil(q * total)) if q > 0 else 1
    seen = 0
    for value, count in sorted(hist.items()):
        seen += count
        if seen >= rank:
            return int(value)
    raise AssertionError("unreachable")


def _hist_summary(hist):
    return {f"p{int(q * 100):02d}": _quantile_from_hist(hist, q)
            for q in (0, .25, .5, .75, .9, .95, .99, 1)}


def analyze(path, split):
    path = Path(path)
    started = time.time()
    totals = Counter()
    field_presence = Counter()
    any_presence = Counter()
    both_presence = Counter()
    occurrence_total = Counter()
    leading_zero = Counter()
    yearlike = Counter()
    longrun = Counter()
    repeated = Counter()
    df = defaultdict(Counter)
    distinct_hist = defaultdict(Counter)
    occurrence_hist = defaultdict(Counter)
    length_hist = defaultdict(Counter)
    rows = 0

    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader)
        if header[:4] != ["entity_id", "business_name", "business_address", "country"]:
            raise ValueError(f"unexpected header: {header!r}")
        for row in reader:
            if len(row) < 4:
                raise ValueError(f"malformed TSV row with {len(row)} columns")
            rows += 1
            country = row[3]
            totals[country] += 1
            fields_present = 0
            for field, index in FIELDS:
                runs = DIGITS.findall(row[index] or "")
                key = (country, field)
                if not runs:
                    distinct_hist[key][0] += 1
                    occurrence_hist[key][0] += 1
                    continue
                fields_present += 1
                field_presence[key] += 1
                occurrence_total[key] += len(runs)
                occurrence_hist[key][len(runs)] += 1
                unique = set(runs)
                distinct_hist[key][len(unique)] += 1
                if len(unique) < len(runs):
                    repeated[key] += 1
                saw_long = False
                for token in runs:
                    length = len(token)
                    length_hist[key][min(length, 10)] += 1
                    if length > 1 and token.startswith("0"):
                        leading_zero[key] += 1
                    if length == 4 and "1900" <= token <= "2099":
                        yearlike[key] += 1
                    saw_long |= length >= 7
                if saw_long:
                    longrun[key] += 1
                for token in unique:
                    df[key][token] += 1
            if fields_present:
                any_presence[country] += 1
            if fields_present == 2:
                both_presence[country] += 1
    pass1 = time.time() - started

    cutoff_coverage = Counter()
    best_df_hist = defaultdict(Counter)
    pass2_started = time.time()
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        next(reader)
        for row in reader:
            country = row[3]
            best_any = None
            for field, index in FIELDS:
                unique = set(DIGITS.findall(row[index] or ""))
                if not unique:
                    continue
                best = min(df[(country, field)][token] for token in unique)
                best_df_hist[(country, field)][best] += 1
                for cutoff in CUTOFFS:
                    if best <= cutoff:
                        cutoff_coverage[(country, field, cutoff)] += 1
                best_any = best if best_any is None else min(best_any, best)
            if best_any is not None:
                best_df_hist[(country, "any")][best_any] += 1
                for cutoff in CUTOFFS:
                    if best_any <= cutoff:
                        cutoff_coverage[(country, "any", cutoff)] += 1
    pass2 = time.time() - pass2_started

    result = {
        "split": split,
        "input_bytes": path.stat().st_size,
        "rows": rows,
        "definition": "maximal ASCII [0-9]+ runs; DF distinct-per-record within split/country/field",
        "runtime_sec": {
            "pass1": round(pass1, 3),
            "pass2": round(pass2, 3),
            "total": round(pass1 + pass2, 3),
        },
        "countries": {},
    }
    for country, n_records in sorted(totals.items()):
        numeric_records = any_presence[country]
        country_result = {
            "records": n_records,
            "any_numeric_records": numeric_records,
            "any_numeric_rate": numeric_records / n_records,
            "both_fields_numeric_records": both_presence[country],
            "both_fields_numeric_rate": both_presence[country] / n_records,
            "fields": {},
        }
        for field, _ in FIELDS:
            key = (country, field)
            present = field_presence[key]
            occurrences = occurrence_total[key]
            token_df = df[key]
            df_hist = Counter(token_df.values())
            types = len(token_df)
            field_result = {
                "records_with_numeric": present,
                "record_rate": present / n_records,
                "distinct_numeric_types": types,
                "numeric_occurrences": occurrences,
                "mean_occurrences_per_numeric_record": occurrences / present if present else 0,
                "record_distinct_token_count_quantiles": _hist_summary(distinct_hist[key]),
                "record_occurrence_count_quantiles": _hist_summary(occurrence_hist[key]),
                "token_type_df_quantiles": _hist_summary(df_hist),
                "best_record_df_quantiles": _hist_summary(best_df_hist[key]),
                "type_share_by_df_cutoff": {},
                "record_coverage_by_df_cutoff": {},
                "digit_run_length_occurrences": {
                    str(k): v for k, v in sorted(length_hist[key].items())
                },
                "digit_run_length_share": {
                    str(k): v / occurrences for k, v in sorted(length_hist[key].items())
                } if occurrences else {},
                "leading_zero_occurrences": leading_zero[key],
                "leading_zero_share": leading_zero[key] / occurrences if occurrences else 0,
                "yearlike_1900_2099_occurrences": yearlike[key],
                "yearlike_share": yearlike[key] / occurrences if occurrences else 0,
                "records_with_run_len_ge_7": longrun[key],
                "run_len_ge_7_record_rate": longrun[key] / n_records,
                "records_with_repeated_numeric_token": repeated[key],
                "repeated_numeric_token_record_rate": repeated[key] / n_records,
            }
            for cutoff in CUTOFFS:
                field_result["type_share_by_df_cutoff"][str(cutoff)] = (
                    sum(count for freq, count in df_hist.items() if freq <= cutoff) / types
                    if types else 0
                )
                covered = cutoff_coverage[(country, field, cutoff)]
                field_result["record_coverage_by_df_cutoff"][str(cutoff)] = {
                    "count": covered,
                    "rate_all_records": covered / n_records,
                    "rate_numeric_records": covered / present if present else 0,
                }
            country_result["fields"][field] = field_result
        country_result["any_field_best_df_quantiles"] = _hist_summary(
            best_df_hist[(country, "any")]
        )
        country_result["any_field_record_coverage_by_df_cutoff"] = {}
        for cutoff in CUTOFFS:
            covered = cutoff_coverage[(country, "any", cutoff)]
            country_result["any_field_record_coverage_by_df_cutoff"][str(cutoff)] = {
                "count": covered,
                "rate_all_records": covered / n_records,
                "rate_numeric_records": covered / numeric_records if numeric_records else 0,
            }
        result["countries"][country] = country_result
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.input, args.split)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "rows": result["rows"],
        "runtime_sec": result["runtime_sec"],
        "countries": {k: v["records"] for k, v in result["countries"].items()},
    }, indent=2))


if __name__ == "__main__":
    main()
