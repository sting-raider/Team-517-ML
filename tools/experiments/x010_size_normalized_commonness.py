from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

TRANSFORMS = ("raw_log1p", "per_million_log1p", "self_information")


def norm_proxy(value: str | None) -> str:
    """Mirror lower(strip_accents)+Unicode alnum+space normalization."""
    value = unicodedata.normalize("NFD", value or "").lower()
    out: list[str] = []
    pending_space = False
    for ch in value:
        if unicodedata.combining(ch):
            continue
        if ch.isalnum():
            if pending_space and out:
                out.append(" ")
            out.append(ch)
            pending_space = False
        else:
            pending_space = True
    return "".join(out).strip()


def fold517(entity_id: str) -> str:
    bucket = int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100
    if bucket < 60:
        return "fit"
    if bucket < 75:
        return "early"
    if bucket < 90:
        return "calibrate"
    return "holdout"


def md5_rank(entity_id: str) -> int:
    return int.from_bytes(hashlib.md5(("sample517:" + entity_id).encode()).digest(), "big")


def _keep_lowest(heap: list, limit: int, rank: int, row: tuple) -> None:
    item = (-rank, row)
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif rank < -heap[0][0]:
        heapq.heapreplace(heap, item)


def scan(path: Path, label: str, chunk_size: int = 100_000, select_top: int = 0):
    counters = defaultdict(lambda: {"name": Counter(), "address": Counter()})
    row_counts = Counter()
    heap: list = []
    started = time.time()
    done = 0
    for chunk in pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        keep_default_na=False,
        usecols=["entity_id", "business_name", "business_address", "country"],
        chunksize=chunk_size,
        engine="c",
        na_filter=False,
    ):
        ids = chunk["entity_id"].tolist()
        countries = chunk["country"].tolist()
        names = [norm_proxy(v) for v in chunk["business_name"].tolist()]
        addresses = [norm_proxy(v) for v in chunk["business_address"].tolist()]
        for entity_id, country, name, address in zip(ids, countries, names, addresses):
            row_counts[country] += 1
            counters[country]["name"][name] += 1
            counters[country]["address"][address] += 1
            if select_top:
                _keep_lowest(heap, select_top, md5_rank(entity_id), (entity_id, country, name, address))
        done += len(chunk)
        print(f"{label}: {done:,} rows in {time.time() - started:.1f}s", flush=True)
    return counters, row_counts, heap, time.time() - started


def raw_frequency_hist(counter: Counter[str]) -> Counter[int]:
    hist: Counter[int] = Counter()
    for text, frequency in counter.items():
        hist[0 if text == "" else frequency] += frequency
    return hist


def transform_value(frequency: int, country_rows: int, transform: str) -> float:
    if frequency == 0:
        return 0.0
    if transform == "raw_log1p":
        return math.log1p(frequency)
    if transform == "per_million_log1p":
        return math.log1p(1_000_000.0 * frequency / country_rows)
    if transform == "self_information":
        return math.log((country_rows + 1.0) / (frequency + 1.0))
    raise ValueError(f"unknown transform: {transform}")


def transform_hist(hist: Counter[int], country_rows: int, transform: str) -> Counter[float]:
    out: Counter[float] = Counter()
    for frequency, count in hist.items():
        out[transform_value(frequency, country_rows, transform)] += count
    return out


def weighted_quantile(hist: Counter[float], q: float) -> float:
    total = sum(hist.values())
    target = q * (total - 1)
    cumulative = 0
    for value in sorted(hist):
        count = hist[value]
        if cumulative + count > target:
            return float(value)
        cumulative += count
    return float(max(hist))


def summarize(hist: Counter[float]) -> dict:
    total = sum(hist.values())
    mean = sum(value * count for value, count in hist.items()) / total
    variance = sum((value - mean) ** 2 * count for value, count in hist.items()) / total
    return {
        "rows": total,
        "mean": mean,
        "std": math.sqrt(variance),
        "min": float(min(hist)),
        "max": float(max(hist)),
        "quantiles": {
            str(q): weighted_quantile(hist, q)
            for q in (0.001, 0.01, 0.5, 0.9, 0.99, 0.999)
        },
    }


def weighted_ks(left: Counter[float], right: Counter[float]) -> float:
    n_left, n_right = sum(left.values()), sum(right.values())
    c_left = c_right = 0
    best = 0.0
    for value in sorted(set(left) | set(right)):
        c_left += left.get(value, 0)
        c_right += right.get(value, 0)
        best = max(best, abs(c_left / n_left - c_right / n_right))
    return best


def selected_fit(heap: list) -> list[tuple]:
    ranked = sorted([(-negative_rank, row) for negative_rank, row in heap], key=lambda item: item[0])
    selected: list[tuple] = []
    for position, (_, row) in enumerate(ranked, start=1):
        entity_id, country, name, address = row
        if position <= 30_000:
            if fold517(entity_id) == "fit":
                selected.append((entity_id, country, name, address, position))
        elif 50_000 < position <= 200_000 and fold517(entity_id) == "fit":
            selected.append((entity_id, country, name, address, position))
    return selected


def run(train_path: Path, test_path: Path, chunk_size: int = 100_000) -> dict:
    train_counters, train_rows, heap, train_seconds = scan(
        train_path, "train", chunk_size=chunk_size, select_top=200_000
    )
    test_counters, test_rows, _, test_seconds = scan(
        test_path, "test", chunk_size=chunk_size
    )
    fit = selected_fit(heap)
    if len(fit) != 108_115:
        raise RuntimeError(f"fit-anchor parity failed: {len(fit)} != 108115")

    population = {"train": defaultdict(dict), "test": defaultdict(dict)}
    for split, counters, rows in (
        ("train", train_counters, train_rows),
        ("test", test_counters, test_rows),
    ):
        for country, fields in counters.items():
            for field, counter in fields.items():
                raw_hist = raw_frequency_hist(counter)
                population[split][country][field] = {
                    transform: transform_hist(raw_hist, rows[country], transform)
                    for transform in TRANSFORMS
                }

    fit_hists = {
        field: {transform: Counter() for transform in TRANSFORMS}
        for field in ("name", "address")
    }
    fit_raw = {field: Counter() for field in ("name", "address")}
    for _, country, name, address, _ in fit:
        for field, text in (("name", name), ("address", address)):
            frequency = 0 if not text else train_counters[country][field][text]
            fit_raw[field][frequency] += 1
            for transform in TRANSFORMS:
                fit_hists[field][transform][
                    transform_value(frequency, train_rows[country], transform)
                ] += 1

    result = {
        "protocol": {
            "population": "complete train/test Source-1; no sampling",
            "normalizer": "Python NFD accent-strip + lower + Unicode alnum/space semantic mirror of v2",
            "fit_selection": "sample517 MD5 positions <=30000 plus 50001:200000 fit-fold only",
            "fit_anchor_count": len(fit),
            "runtime_seconds": {"train_scan": train_seconds, "test_scan": test_seconds},
        },
        "row_counts": {"train": dict(train_rows), "test": dict(test_rows)},
        "same_country_train_test": {},
        "fit_support": {},
        "test_vs_fit": {},
    }

    for country in sorted(set(train_rows) & set(test_rows)):
        result["same_country_train_test"][country] = {}
        for field in ("name", "address"):
            result["same_country_train_test"][country][field] = {}
            for transform in TRANSFORMS:
                train_hist = population["train"][country][field][transform]
                test_hist = population["test"][country][field][transform]
                train_summary, test_summary = summarize(train_hist), summarize(test_hist)
                result["same_country_train_test"][country][field][transform] = {
                    "weighted_ks": weighted_ks(train_hist, test_hist),
                    "mean_train": train_summary["mean"],
                    "mean_test": test_summary["mean"],
                    "mean_delta": test_summary["mean"] - train_summary["mean"],
                }

    for field in ("name", "address"):
        result["fit_support"][field] = {"raw_frequency_max": max(fit_raw[field])}
        for transform in TRANSFORMS:
            result["fit_support"][field][transform] = summarize(fit_hists[field][transform])

    for country in sorted(test_rows):
        result["test_vs_fit"][country] = {}
        for field in ("name", "address"):
            result["test_vs_fit"][country][field] = {}
            for transform in TRANSFORMS:
                test_hist = population["test"][country][field][transform]
                fit_summary = summarize(fit_hists[field][transform])
                total = sum(test_hist.values())
                lo, hi = fit_summary["min"], fit_summary["max"]
                qlo = fit_summary["quantiles"]["0.001"]
                qhi = fit_summary["quantiles"]["0.999"]
                result["test_vs_fit"][country][field][transform] = {
                    "outside_fit_minmax_rate": sum(
                        count for value, count in test_hist.items() if value < lo or value > hi
                    ) / total,
                    "below_fit_min_rate": sum(
                        count for value, count in test_hist.items() if value < lo
                    ) / total,
                    "above_fit_max_rate": sum(
                        count for value, count in test_hist.items() if value > hi
                    ) / total,
                    "outside_fit_p001_p999_rate": sum(
                        count for value, count in test_hist.items() if value < qlo or value > qhi
                    ) / total,
                    "test_summary": summarize(test_hist),
                }

    expected_ks = {
        ("US", "name"): 0.0669,
        ("US", "address"): 0.0158,
        ("India", "name"): 0.0344,
        ("India", "address"): 0.0015,
    }
    for (country, field), expected in expected_ks.items():
        actual = result["same_country_train_test"][country][field]["raw_log1p"]["weighted_ks"]
        if abs(actual - expected) >= 0.001:
            raise RuntimeError(
                f"X009 raw-frequency parity failed for {country}/{field}: {actual} vs {expected}"
            )
    if result["fit_support"]["name"]["raw_frequency_max"] != 253:
        raise RuntimeError("X009 name-frequency fit-support parity failed")
    if result["fit_support"]["address"]["raw_frequency_max"] != 14:
        raise RuntimeError("X009 address-frequency fit-support parity failed")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    args = parser.parse_args()
    result = run(args.train, args.test, args.chunk_size)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
