from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import resource
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


TRANSFORMS = ("raw_log1p", "per_million", "self_information")


def norm_proxy(value: str | None) -> str:
    """Semantic mirror of lower(strip_accents)+Unicode alnum+space normalization."""
    value = unicodedata.normalize("NFD", value or "").lower()
    out = []
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
    bucket = int(
        hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16
    ) % 100
    if bucket < 60:
        return "fit"
    if bucket < 75:
        return "early"
    if bucket < 90:
        return "calibrate"
    return "holdout"


def md5_rank(entity_id: str) -> int:
    return int.from_bytes(
        hashlib.md5(("sample517:" + entity_id).encode()).digest(), "big"
    )


def keep_lowest(heap: list, limit: int, rank: int, row: tuple) -> None:
    item = (-rank, row)
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif rank < -heap[0][0]:
        heapq.heapreplace(heap, item)


def scan(path: Path, split: str, chunk_size: int = 100000, select_top: int = 0):
    counters = defaultdict(lambda: {"name": Counter(), "address": Counter()})
    rows = Counter()
    heap = []
    started = time.time()
    done = 0
    cols = ["entity_id", "business_name", "business_address", "country"]

    for chunk in pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        keep_default_na=False,
        usecols=cols,
        chunksize=chunk_size,
        engine="c",
        na_filter=False,
    ):
        ids = chunk["entity_id"].tolist()
        countries = chunk["country"].tolist()
        names = [norm_proxy(x) for x in chunk["business_name"].tolist()]
        addresses = [norm_proxy(x) for x in chunk["business_address"].tolist()]
        for entity_id, country, name, address in zip(
            ids, countries, names, addresses
        ):
            rows[country] += 1
            counters[country]["name"][name] += 1
            counters[country]["address"][address] += 1
            if select_top:
                keep_lowest(
                    heap,
                    select_top,
                    md5_rank(entity_id),
                    (entity_id, country, name, address),
                )
        done += len(chunk)
        if done % 500000 < chunk_size:
            print(
                f"{split}: {done:,} rows / {time.time() - started:.1f}s",
                flush=True,
            )

    return counters, rows, heap, time.time() - started


def row_frequency_hist(counter: Counter[str]) -> Counter[int]:
    hist = Counter()
    for text, freq in counter.items():
        hist[0 if text == "" else freq] += freq
    return hist


def transform_value(freq: int, country_rows: int, kind: str) -> float:
    if freq <= 0:
        return 0.0
    if kind == "raw_log1p":
        return math.log1p(freq)
    if kind == "per_million":
        return math.log1p(1_000_000.0 * freq / country_rows)
    if kind == "self_information":
        return math.log((country_rows + 1.0) / (freq + 1.0))
    raise KeyError(kind)


def transformed_hist(freq_hist: Counter[int], country_rows: int, kind: str):
    out = defaultdict(int)
    for freq, count in freq_hist.items():
        out[transform_value(freq, country_rows, kind)] += count
    return dict(out)


def weighted_quantile(hist, q: float) -> float:
    total = sum(hist.values())
    if not total:
        return float("nan")
    target = q * (total - 1)
    cumulative = 0
    for value in sorted(hist):
        count = hist[value]
        if cumulative + count > target:
            return float(value)
        cumulative += count
    return float(max(hist))


def weighted_ks(left, right) -> float:
    n_left = sum(left.values())
    n_right = sum(right.values())
    keys = sorted(set(left) | set(right))
    c_left = c_right = 0
    best = 0.0
    for key in keys:
        c_left += left.get(key, 0)
        c_right += right.get(key, 0)
        best = max(best, abs(c_left / n_left - c_right / n_right))
    return best


def summarize(hist) -> dict:
    total = sum(hist.values())
    mean = sum(value * count for value, count in hist.items()) / total
    variance = (
        sum((value - mean) ** 2 * count for value, count in hist.items()) / total
    )
    return {
        "rows": total,
        "mean": mean,
        "std": math.sqrt(variance),
        "p001": weighted_quantile(hist, 0.001),
        "p01": weighted_quantile(hist, 0.01),
        "p50": weighted_quantile(hist, 0.5),
        "p99": weighted_quantile(hist, 0.99),
        "p999": weighted_quantile(hist, 0.999),
        "min": float(min(hist)),
        "max": float(max(hist)),
    }


def select_fit(heap, counters, row_counts):
    ranked = sorted([(-neg, row) for neg, row in heap], key=lambda item: item[0])
    selected = []
    for position, (_, row) in enumerate(ranked, start=1):
        entity_id, country, name, address = row
        if position <= 30000:
            if fold517(entity_id) == "fit":
                selected.append((entity_id, country, name, address, position))
        elif 50000 < position <= 200000 and fold517(entity_id) == "fit":
            selected.append((entity_id, country, name, address, position))

    fit_hists = {
        field: {kind: defaultdict(int) for kind in TRANSFORMS}
        for field in ("name", "address")
    }
    by_country = Counter()
    for _, country, name, address, _ in selected:
        by_country[country] += 1
        country_rows = row_counts[country]
        for field, text in (("name", name), ("address", address)):
            freq = 0 if text == "" else counters[country][field][text]
            for kind in TRANSFORMS:
                fit_hists[field][kind][
                    transform_value(freq, country_rows, kind)
                ] += 1
    return selected, fit_hists, by_country


def outside_fit_range(test_hist, fit_hist) -> dict:
    lower = min(fit_hist)
    upper = max(fit_hist)
    total = sum(test_hist.values())
    below = sum(count for value, count in test_hist.items() if value < lower)
    above = sum(count for value, count in test_hist.items() if value > upper)
    return {
        "fit_min": float(lower),
        "fit_max": float(upper),
        "below_fit_min_rows": below,
        "below_fit_min_rate": below / total,
        "above_fit_max_rows": above,
        "above_fit_max_rate": above / total,
        "outside_fit_range_rows": below + above,
        "outside_fit_range_rate": (below + above) / total,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100000)
    args = parser.parse_args()

    assert norm_proxy("  Café--12/A  ") == "cafe 12 a"
    assert norm_proxy("Müller & Söhne") == "muller sohne"

    train_counters, train_rows, heap, train_seconds = scan(
        args.train, "train", args.chunk_size, 200000
    )
    test_counters, test_rows, _, test_seconds = scan(
        args.test, "test", args.chunk_size, 0
    )
    selected, fit_hists, fit_country = select_fit(
        heap, train_counters, train_rows
    )
    if len(selected) != 108115:
        raise RuntimeError(
            f"INT002/INT003 fit count {len(selected)} != expected 108115"
        )

    result = {
        "experiment_id": "X010",
        "population": {
            "train_rows": sum(train_rows.values()),
            "test_rows": sum(test_rows.values()),
            "train_country_rows": dict(train_rows),
            "test_country_rows": dict(test_rows),
        },
        "fit": {
            "anchors": len(selected),
            "country_anchors": dict(fit_country),
            "features": {},
        },
        "same_country_train_test": {},
        "france_vs_fit": {},
        "runtime_seconds": {
            "train_scan": train_seconds,
            "test_scan": test_seconds,
            "scan_total": train_seconds + test_seconds,
        },
        "integrity": {
            "normalization_examples": True,
            "fit_anchor_count_reproduced": len(selected) == 108115,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
    }

    for field in ("name", "address"):
        result["fit"]["features"][field] = {
            kind: summarize(fit_hists[field][kind]) for kind in TRANSFORMS
        }

    raw_name_max = math.expm1(
        result["fit"]["features"]["name"]["raw_log1p"]["max"]
    )
    raw_address_max = math.expm1(
        result["fit"]["features"]["address"]["raw_log1p"]["max"]
    )
    if not math.isclose(raw_name_max, 253.0) or not math.isclose(
        raw_address_max, 14.0
    ):
        raise RuntimeError(
            "X009 parity failure: expected raw fit maxima 253/14, "
            f"got {raw_name_max}/{raw_address_max}"
        )
    result["integrity"]["x009_fit_raw_name_max_freq_equivalent"] = raw_name_max
    result["integrity"][
        "x009_fit_raw_address_max_freq_equivalent"
    ] = raw_address_max

    for country in sorted(set(train_counters) & set(test_counters)):
        result["same_country_train_test"][country] = {}
        for field in ("name", "address"):
            train_freq = row_frequency_hist(train_counters[country][field])
            test_freq = row_frequency_hist(test_counters[country][field])
            result["same_country_train_test"][country][field] = {}
            for kind in TRANSFORMS:
                train_hist = transformed_hist(
                    train_freq, train_rows[country], kind
                )
                test_hist = transformed_hist(
                    test_freq, test_rows[country], kind
                )
                train_summary = summarize(train_hist)
                test_summary = summarize(test_hist)
                result["same_country_train_test"][country][field][kind] = {
                    "weighted_ks": weighted_ks(train_hist, test_hist),
                    "train_mean": train_summary["mean"],
                    "test_mean": test_summary["mean"],
                    "mean_delta": test_summary["mean"] - train_summary["mean"],
                    "train_min": train_summary["min"],
                    "train_max": train_summary["max"],
                    "test_min": test_summary["min"],
                    "test_max": test_summary["max"],
                }

    for field in ("name", "address"):
        france_freq = row_frequency_hist(test_counters["France"][field])
        result["france_vs_fit"][field] = {}
        for kind in TRANSFORMS:
            france_hist = transformed_hist(
                france_freq, test_rows["France"], kind
            )
            result["france_vs_fit"][field][kind] = {
                **outside_fit_range(france_hist, fit_hists[field][kind]),
                "france": summarize(france_hist),
            }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
