"""Full Source-1 feasibility census for address-number + text composite retrieval keys.

Analysis-only: Source-1 document frequency is a collision/selectivity proxy, not
target-side candidate recall or a competition-score measurement.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

CUTOFFS = (1, 2, 5, 10, 50, 100, 1000)
SEP = "|#|"
ADDRESS_STOPWORDS = {
    "road", "street", "avenue", "drive", "lane", "floor", "near",
    "opposite", "the", "and", "unit", "plot", "no",
}
DIGITS = re.compile(r"[0-9]+")


def norm(value: str | None) -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def evidence(name: str | None, address: str | None):
    n = norm(name)
    a = norm(address)
    match = DIGITS.search(a)
    number = match.group(0) if match else None
    name_words = {w for w in n.split() if len(w) >= 3}
    address_words = {
        w for w in a.split()
        if len(w) >= 3 and not w.isdigit() and w not in ADDRESS_STOPWORDS
    }
    return number, name_words, address_words


def _iter_rows(path: Path, country: str):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"business_name", "business_address", "country"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        for row in reader:
            if row["country"] == country:
                yield row


def _quantiles(hist: Counter[int], quantiles=(0.5, 0.9, 0.95, 0.99)):
    total = sum(hist.values())
    if not total:
        return {str(q): None for q in quantiles}
    ordered = sorted(hist.items())
    out = {}
    for q in quantiles:
        target = max(1, math.ceil(q * total))
        seen = 0
        for df, count in ordered:
            seen += count
            if seen >= target:
                out[str(q)] = df
                break
    return out


def _finish_family(hist: Counter[int], rows: int, available: int, emitted: int):
    return {
        "available_rows": available,
        "available_rate": available / rows if rows else 0.0,
        "mean_emitted_keys_per_row": emitted / rows if rows else 0.0,
        "best_df_quantiles_among_available": _quantiles(hist),
        "coverage": {
            str(c): sum(n for df, n in hist.items() if df <= c) / rows if rows else 0.0
            for c in CUTOFFS
        },
    }


def analyze_country(path: Path, country: str):
    number_df: Counter[str] = Counter()
    num_name_df: Counter[str] = Counter()
    num_address_df: Counter[str] = Counter()
    rows = 0

    for row in _iter_rows(path, country):
        rows += 1
        number, name_words, address_words = evidence(
            row["business_name"], row["business_address"]
        )
        if not number:
            continue
        number_df[number] += 1
        num_name_df.update({number + SEP + w for w in name_words})
        num_address_df.update({number + SEP + w for w in address_words})

    hists = {k: Counter() for k in ("number", "number_name", "number_address")}
    available = Counter()
    emitted = Counter()
    rescue = {"number_name": Counter(), "number_address": Counter()}

    for row in _iter_rows(path, country):
        number, name_words, address_words = evidence(
            row["business_name"], row["business_address"]
        )
        if not number:
            continue

        base_df = number_df[number]
        hists["number"][base_df] += 1
        available["number"] += 1
        emitted["number"] += 1

        name_keys = {number + SEP + w for w in name_words}
        emitted["number_name"] += len(name_keys)
        if name_keys:
            best = min(num_name_df[k] for k in name_keys)
            hists["number_name"][best] += 1
            available["number_name"] += 1
            for cutoff in CUTOFFS:
                if base_df > cutoff and best <= cutoff:
                    rescue["number_name"][cutoff] += 1

        address_keys = {number + SEP + w for w in address_words}
        emitted["number_address"] += len(address_keys)
        if address_keys:
            best = min(num_address_df[k] for k in address_keys)
            hists["number_address"][best] += 1
            available["number_address"] += 1
            for cutoff in CUTOFFS:
                if base_df > cutoff and best <= cutoff:
                    rescue["number_address"][cutoff] += 1

    result = {
        "country": country,
        "rows": rows,
        "families": {
            key: _finish_family(hists[key], rows, available[key], emitted[key])
            for key in hists
        },
        "rescue_over_number_only": {},
    }
    for family in ("number_name", "number_address"):
        result["rescue_over_number_only"][family] = {
            str(c): {
                "rows": rescue[family][c],
                "rate_of_all_rows": rescue[family][c] / rows if rows else 0.0,
            }
            for c in CUTOFFS
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source1", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "test"), required=True)
    parser.add_argument("--countries", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    result = {
        "experiment": "F014",
        "split": args.split,
        "cutoffs": list(CUTOFFS),
        "semantics": {
            "number": "first normalized address digit run",
            "number_name": "first address number + each distinct normalized name token len>=3",
            "number_address": "first address number + each distinct production-style address word (production d: family)",
            "df_scope": "split + country + Source-1 only",
        },
        "countries": {
            country: analyze_country(args.source1, country)
            for country in args.countries
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
