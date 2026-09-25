"""R004 Tier-1 feasibility audit for bounded mixed name/address char n-gram probes.

This intentionally does not implement target retrieval. It measures whether a fixed
small rare-probe budget is plausible on the exact calibration anchors using a
reproducible Source-1 corpus-frequency proxy. Full S2/S3 target data are required
before any retrieval-recall/oracle claim is valid.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import resource
import time
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np


def norm_proxy(value: str | None) -> str:
    """Semantic Python proxy for repo DuckDB lower(strip_accents)+Unicode cleanup."""
    value = unicodedata.normalize("NFKD", value or "").lower()
    out = []
    previous_space = True
    for char in value:
        if unicodedata.combining(char):
            continue
        if char.isalnum():
            out.append(char)
            previous_space = False
        elif not previous_space:
            out.append(" ")
            previous_space = True
    return "".join(out).strip()


def char_ngrams(value: str | None) -> set[str]:
    compact = norm_proxy(value).replace(" ", "")
    grams = set()
    for n in (3, 4, 5):
        if len(compact) >= n:
            grams.update(compact[i:i + n] for i in range(len(compact) - n + 1))
    return grams


def md5_rank(prefix: str, entity_id: str) -> int:
    return int(hashlib.md5((prefix + entity_id).encode()).hexdigest(), 16)


def fold517(entity_id: str) -> str:
    bucket = int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100
    return "fit" if bucket < 60 else "early" if bucket < 75 else "calibrate" if bucket < 90 else "holdout"


def keep_smallest(heap: list, limit: int, rank: int, row: tuple[str, str, str, str]) -> None:
    item = (-rank, row)
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif rank < -heap[0][0]:
        heapq.heapreplace(heap, item)


def cardinality_bucket(value: int) -> str:
    if value == 0:
        return "0"
    if value == 1:
        return "1"
    if value <= 4:
        return "2-4"
    return "5+"


def quantiles(values: list[int]) -> dict[str, float] | None:
    if not values:
        return None
    array = np.asarray(values, dtype=float)
    return {
        "p50": float(np.quantile(array, 0.50)),
        "p90": float(np.quantile(array, 0.90)),
        "p99": float(np.quantile(array, 0.99)),
        "max": float(array.max()),
        "mean": float(array.mean()),
    }


def run(source1: Path, truth: Path, out: Path, dev_n: int, df_sample_n: int, df_seed: str) -> dict:
    started = time.time()
    dev_heap = []
    df_heap = []
    source1_rows = 0

    with source1.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            source1_rows += 1
            entity_id = row["entity_id"]
            packed = (
                entity_id,
                row.get("business_name", ""),
                row.get("business_address", ""),
                row.get("country", ""),
            )
            keep_smallest(dev_heap, dev_n, md5_rank("sample517:", entity_id), packed)
            keep_smallest(df_heap, df_sample_n, md5_rank(df_seed, entity_id), packed)

    dev_rows = [item[1] for item in dev_heap]
    calibration = [row for row in dev_rows if fold517(row[0]) == "calibrate"]
    calibration_ids = {row[0] for row in calibration}

    truth_cardinality = {}
    with truth.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            entity_id = row["source1_entity_id"]
            if entity_id not in calibration_ids:
                continue
            matches = (row.get("matched_entity_ids") or "").strip()
            truth_cardinality[entity_id] = 0 if not matches else sum(bool(x) for x in matches.split(","))
    if len(truth_cardinality) != len(calibration):
        raise RuntimeError(f"truth coverage mismatch: {len(truth_cardinality)} != {len(calibration)}")

    per_anchor = {}
    name_universe = set()
    address_universe = set()
    for entity_id, name, address, country in calibration:
        name_grams = char_ngrams(name)
        address_grams = char_ngrams(address)
        per_anchor[entity_id] = (name_grams, address_grams, country, truth_cardinality[entity_id])
        name_universe.update(name_grams)
        address_universe.update(address_grams)

    name_df = Counter()
    address_df = Counter()
    for _, packed in df_heap:
        _, name, address, _ = packed
        for gram in char_ngrams(name):
            if gram in name_universe:
                name_df[gram] += 1
        for gram in char_ngrams(address):
            if gram in address_universe:
                address_df[gram] += 1

    def summarize(entity_ids: list[str]) -> dict:
        values = {k: [] for k in (
            "n_grams_name", "n_grams_addr", "min_df_name", "min_df_addr",
            "mass_name4", "mass_addr4", "mass_mixed8",
        )}
        flags = Counter()
        for entity_id in entity_ids:
            name_grams, address_grams, _, _ = per_anchor[entity_id]
            name_counts = sorted(name_df.get(gram, 0) for gram in name_grams)
            address_counts = sorted(address_df.get(gram, 0) for gram in address_grams)
            values["n_grams_name"].append(len(name_grams))
            values["n_grams_addr"].append(len(address_grams))
            if name_counts:
                values["min_df_name"].append(name_counts[0])
            if address_counts:
                values["min_df_addr"].append(address_counts[0])
            name_mass = sum(name_counts[:4])
            address_mass = sum(address_counts[:4])
            values["mass_name4"].append(name_mass)
            values["mass_addr4"].append(address_mass)
            values["mass_mixed8"].append(name_mass + address_mass)
            flags["has_name"] += bool(name_counts)
            flags["has_addr"] += bool(address_counts)
            flags["has_both"] += bool(name_counts and address_counts)
            mixed = sorted(name_counts + address_counts)
            for threshold in (1, 5, 10, 25, 50, 100, 250):
                flags[f"name4_df_le_{threshold}"] += len(name_counts) >= 4 and name_counts[3] <= threshold
                flags[f"addr4_df_le_{threshold}"] += len(address_counts) >= 4 and address_counts[3] <= threshold
                flags[f"mixed_any4_df_le_{threshold}"] += len(mixed) >= 4 and mixed[3] <= threshold
        n = len(entity_ids)
        return {
            "n": n,
            "quantiles": {key: quantiles(value) for key, value in values.items()},
            "fractions": {key: value / n for key, value in flags.items()},
        }

    all_ids = [row[0] for row in calibration]
    result = {
        "protocol": {
            "source1_rows": source1_rows,
            "dev_n": dev_n,
            "calibration_n": len(calibration),
            "df_proxy_sample_n": df_sample_n,
            "df_proxy_fraction": df_sample_n / source1_rows,
            "df_seed": df_seed,
            "normalizer": "Python NFKD accent-strip + Unicode alnum; semantic proxy for repo DuckDB strip_accents",
            "ngrams": [3, 4, 5],
            "probe_policy": "four lowest Source1-sample-DF grams per field; mixed is up to eight probes total",
        },
        "calibration_country_counts": dict(Counter(per_anchor[x][2] for x in all_ids)),
        "truth_cardinality_counts": dict(Counter(cardinality_bucket(per_anchor[x][3]) for x in all_ids)),
        "overall": summarize(all_ids),
        "by_country": {},
        "by_cardinality": {},
        "gram_universe": {"name": len(name_universe), "address": len(address_universe)},
        "runtime_seconds": time.time() - started,
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    for country in sorted({per_anchor[x][2] for x in all_ids}):
        result["by_country"][country] = summarize([x for x in all_ids if per_anchor[x][2] == country])
    for bucket in ("0", "1", "2-4", "5+"):
        result["by_cardinality"][bucket] = summarize(
            [x for x in all_ids if cardinality_bucket(per_anchor[x][3]) == bucket]
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source1", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dev-n", type=int, default=30_000)
    parser.add_argument("--df-sample-n", type=int, default=50_000)
    parser.add_argument("--df-seed", default="r004df517:")
    args = parser.parse_args()
    result = run(args.source1, args.truth, args.out, args.dev_n, args.df_sample_n, args.df_seed)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
