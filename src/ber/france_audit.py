"""Aggregate source-one text-shift audit for unseen-country robustness.

This deliberately emits only aggregate statistics. The NFKD fold is a diagnostic
proxy for accent sensitivity; production normalization remains defined in data.py
with DuckDB strip_accents().
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

WORD_RE = re.compile(r"\w+", re.UNICODE)
DIGIT_RE = re.compile(r"\d", re.UNICODE)
BLOCK_STOPWORDS = {
    "road", "street", "avenue", "drive", "lane", "floor", "near", "opposite",
    "the", "and", "unit", "plot", "no",
}


def nfkd_fold(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def word_tokens(text: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(text)]


def normalized_token_string(text: str, *, fold: bool) -> str:
    if fold:
        text = nfkd_fold(text)
    return " ".join(word_tokens(text))


def eligible_word_tokens(text: str) -> list[str]:
    return [
        token for token in word_tokens(text)
        if len(token) >= 3 and not token.isdigit() and token not in BLOCK_STOPWORDS
    ]


def new_field_accumulator() -> dict[str, float]:
    return {
        "records": 0,
        "empty": 0,
        "nonascii": 0,
        "nfkd_fold_changed": 0,
        "has_digit": 0,
        "hyphen": 0,
        "apostrophe": 0,
        "eligible_word_token_empty_proxy": 0,
        "chars": 0,
        "tokens": 0,
    }


def update_field(acc: dict[str, float], text: str) -> None:
    tokens = word_tokens(text)
    acc["records"] += 1
    acc["empty"] += not text
    acc["nonascii"] += any(ord(char) > 127 for char in text)
    acc["nfkd_fold_changed"] += nfkd_fold(text) != text
    acc["has_digit"] += bool(DIGIT_RE.search(text))
    acc["hyphen"] += "-" in text
    acc["apostrophe"] += "'" in text or "\u2019" in text
    acc["eligible_word_token_empty_proxy"] += not eligible_word_tokens(text)
    acc["chars"] += len(text)
    acc["tokens"] += len(tokens)


def summarize_field(acc: dict[str, float]) -> dict[str, float]:
    n = int(acc["records"])
    if not n:
        return {"records": 0}

    def pct(key: str) -> float:
        return 100.0 * float(acc[key]) / n

    return {
        "records": n,
        "empty_pct": pct("empty"),
        "nonascii_pct": pct("nonascii"),
        "nfkd_fold_changed_pct": pct("nfkd_fold_changed"),
        "has_digit_pct": pct("has_digit"),
        "hyphen_pct": pct("hyphen"),
        "apostrophe_pct": pct("apostrophe"),
        "eligible_word_token_empty_proxy_pct": pct("eligible_word_token_empty_proxy"),
        "mean_chars": float(acc["chars"]) / n,
        "mean_tokens": float(acc["tokens"]) / n,
    }


def scan_source1(path: Path, france_details: bool) -> dict:
    by_country: dict[str, dict[str, dict[str, float]]] = {}
    france_name_keep: set[str] = set()
    france_name_fold: set[str] = set()
    france_address_keep: set[str] = set()
    france_address_fold: set[str] = set()
    france_name_tokens: Counter[str] = Counter()
    france_address_tokens: Counter[str] = Counter()

    started = time.time()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"business_name", "business_address", "country"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError(f"{path} missing required columns: {sorted(required)}")
        for row in reader:
            country = row["country"] or ""
            fields = by_country.setdefault(
                country, {"name": new_field_accumulator(), "address": new_field_accumulator()}
            )
            name = row["business_name"] or ""
            address = row["business_address"] or ""
            update_field(fields["name"], name)
            update_field(fields["address"], address)
            if france_details and country == "France":
                name_keep = normalized_token_string(name, fold=False)
                name_fold = normalized_token_string(name, fold=True)
                address_keep = normalized_token_string(address, fold=False)
                address_fold = normalized_token_string(address, fold=True)
                france_name_keep.add(name_keep)
                france_name_fold.add(name_fold)
                france_address_keep.add(address_keep)
                france_address_fold.add(address_fold)
                france_name_tokens.update(word_tokens(nfkd_fold(name)))
                france_address_tokens.update(word_tokens(nfkd_fold(address)))

    result = {
        "path": str(path),
        "elapsed_seconds": time.time() - started,
        "countries": {
            country: {
                "records": int(fields["name"]["records"]),
                "name": summarize_field(fields["name"]),
                "address": summarize_field(fields["address"]),
            }
            for country, fields in sorted(by_country.items())
        },
    }
    if france_details:
        result["france_details"] = {
            "name_distinct_token_normalized_preserve_diacritics": len(france_name_keep),
            "name_distinct_token_normalized_nfkd_fold": len(france_name_fold),
            "name_distinct_collapsed_by_nfkd_fold": len(france_name_keep) - len(france_name_fold),
            "address_distinct_token_normalized_preserve_diacritics": len(france_address_keep),
            "address_distinct_token_normalized_nfkd_fold": len(france_address_fold),
            "address_distinct_collapsed_by_nfkd_fold": len(france_address_keep) - len(france_address_fold),
            "top_name_tokens_nfkd_folded": france_name_tokens.most_common(25),
            "top_address_tokens_nfkd_folded": france_address_tokens.most_common(40),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-source1", type=Path, required=True)
    parser.add_argument("--test-source1", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = {
        "protocol": (
            "Full source-one census. NFKD fold is diagnostic only; production uses "
            "DuckDB strip_accents() in src/ber/data.py. No row-level data is emitted."
        ),
        "train": scan_source1(args.train_source1, france_details=False),
        "test": scan_source1(args.test_source1, france_details=True),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
