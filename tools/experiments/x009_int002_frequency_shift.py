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


def norm_proxy(value: str | None) -> str:
    """Mirror lower(strip_accents)+Unicode letters/numbers+space normalization."""
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


def keep_lowest(heap: list, limit: int, rank: int, row: tuple) -> None:
    item = (-rank, row)
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif rank < -heap[0][0]:
        heapq.heapreplace(heap, item)


def weighted_quantile(hist: Counter[int], q: float) -> float:
    total = sum(hist.values())
    if total == 0:
        return float("nan")
    target = q * (total - 1)
    cumulative = 0
    for value in sorted(hist):
        count = hist[value]
        if cumulative + count > target:
            return float(value)
        cumulative += count
    return float(max(hist))


def freq_hist(counter: Counter[str]) -> Counter[int]:
    hist = Counter()
    for text, freq in counter.items():
        if text == "":
            hist[0] += freq
        else:
            hist[freq] += freq
    return hist


def hist_stats(counter: Counter[str]) -> dict:
    hist = freq_hist(counter)
    rows = sum(hist.values())
    empty = hist.get(0, 0)
    nonempty = rows - empty
    collided = sum(count for f, count in hist.items() if f > 1)
    mean_log = sum(math.log1p(f) * count for f, count in hist.items()) / rows
    second_log = sum((math.log1p(f) ** 2) * count for f, count in hist.items()) / rows
    q_levels = [0.5, 0.9, 0.99, 0.999, 1.0]
    fq = {str(q): weighted_quantile(hist, q) for q in q_levels}
    return {
        "rows": rows,
        "empty_rows": empty,
        "empty_rate": empty / rows,
        "unique_nonempty_values": len(counter) - (1 if "" in counter else 0),
        "collision_row_rate_all": collided / rows,
        "collision_row_rate_nonempty": collided / nonempty if nonempty else None,
        "mean_log1p_frequency": mean_log,
        "std_log1p_frequency": math.sqrt(max(0.0, second_log - mean_log * mean_log)),
        "frequency_quantiles": fq,
        "log1p_frequency_quantiles": {q: math.log1p(v) for q, v in fq.items()},
        "max_frequency": max(hist) if hist else None,
        "row_rates_ge_frequency": {
            str(t): sum(count for f, count in hist.items() if f >= t) / rows
            for t in [2, 3, 5, 10, 25, 50, 100, 250, 500, 1000]
        },
        "feature_frequency_hist": dict(sorted(hist.items())),
    }


def weighted_ks(h1, h2) -> float:
    a = {int(k): int(v) for k, v in h1.items()}
    b = {int(k): int(v) for k, v in h2.items()}
    n1, n2 = sum(a.values()), sum(b.values())
    keys = sorted(set(a) | set(b))
    c1 = c2 = 0
    best = 0.0
    for k in keys:
        c1 += a.get(k, 0)
        c2 += b.get(k, 0)
        best = max(best, abs(c1 / n1 - c2 / n2))
    return best


def scan(path: Path, split: str, chunk_size: int, select_top: int = 0):
    counters = defaultdict(lambda: {"name": Counter(), "address": Counter()})
    row_counts = Counter()
    heap = []
    started = time.time()
    done = 0
    cols = ["entity_id", "business_name", "business_address", "country"]
    for chunk in pd.read_csv(
        path, sep="\t", dtype=str, keep_default_na=False, usecols=cols,
        chunksize=chunk_size, engine="c", na_filter=False
    ):
        ids = chunk["entity_id"].tolist()
        countries = chunk["country"].tolist()
        names = [norm_proxy(x) for x in chunk["business_name"].tolist()]
        addrs = [norm_proxy(x) for x in chunk["business_address"].tolist()]
        for entity_id, country, n, a in zip(ids, countries, names, addrs):
            row_counts[country] += 1
            counters[country]["name"][n] += 1
            counters[country]["address"][a] += 1
            if select_top:
                keep_lowest(heap, select_top, md5_rank(entity_id), (entity_id, country, n, a))
        done += len(chunk)
        print(f"{split}: {done:,} rows in {time.time()-started:.1f}s", flush=True)
    return counters, row_counts, heap, time.time() - started


def selected_fit_stats(heap, counters):
    ranked = sorted([(-neg, row) for neg, row in heap], key=lambda x: x[0])
    selected = []
    for pos, (_, row) in enumerate(ranked, start=1):
        entity_id, country, n, a = row
        if pos <= 30000:
            if fold517(entity_id) == "fit":
                selected.append((entity_id, country, n, a, pos))
        elif 50000 < pos <= 200000 and fold517(entity_id) == "fit":
            selected.append((entity_id, country, n, a, pos))
    stats = defaultdict(lambda: {"name": Counter(), "address": Counter(), "anchors": 0})
    for _, country, n, a, _ in selected:
        stats[country]["anchors"] += 1
        nf = 0 if not n else counters[country]["name"][n]
        af = 0 if not a else counters[country]["address"][a]
        stats[country]["name"][nf] += 1
        stats[country]["address"][af] += 1
    global_stats = {"name": Counter(), "address": Counter(), "anchors": len(selected)}
    for country in stats:
        global_stats["name"].update(stats[country]["name"])
        global_stats["address"].update(stats[country]["address"])
    return selected, stats, global_stats


def hist_summary(hist: Counter[int]) -> dict:
    rows = sum(hist.values())
    fq = {str(q): weighted_quantile(hist, q) for q in [0.5, 0.9, 0.99, 0.999, 1.0]}
    return {
        "rows": rows,
        "mean_log1p_frequency": sum(math.log1p(f)*c for f,c in hist.items())/rows,
        "frequency_quantiles": fq,
        "log1p_frequency_quantiles": {q: math.log1p(v) for q,v in fq.items()},
        "max_frequency": max(hist) if hist else None,
        "support_values": sorted(hist),
    }


def oos_vs_fit(test_hist, fit_hist: Counter[int]) -> dict:
    th = {int(k): int(v) for k,v in test_hist.items()}
    total = sum(th.values())
    support = set(fit_hist)
    fit_max = max(support)
    p999 = weighted_quantile(fit_hist, 0.999)
    return {
        "fit_max_frequency": fit_max,
        "fit_p999_frequency": p999,
        "numeric_value_unseen_in_fit_rate": sum(c for f,c in th.items() if f not in support)/total,
        "above_fit_max_rate": sum(c for f,c in th.items() if f > fit_max)/total,
        "above_fit_p999_rate": sum(c for f,c in th.items() if f > p999)/total,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--test", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--chunk-size", type=int, default=100000)
    args = ap.parse_args()

    cases = {
        "  Café--12/A  ": "cafe 12 a",
        "Müller & Söhne": "muller sohne",
        "SHOP # 007": "shop 007",
        "": "",
    }
    got = {k: norm_proxy(k) for k in cases}
    if got != cases:
        raise AssertionError((got, cases))

    train_c, train_rows, heap, train_seconds = scan(args.train, "train", args.chunk_size, select_top=200000)
    test_c, test_rows, _, test_seconds = scan(args.test, "test", args.chunk_size, select_top=0)
    selected, fit_by_country, fit_global = selected_fit_stats(heap, train_c)
    if len(selected) != 108115:
        raise RuntimeError(f"INT002 fit-anchor reproduction failed: {len(selected)} != 108115")

    result = {
        "protocol": {
            "train_file": str(args.train), "test_file": str(args.test),
            "normalizer": "Python NFD accent-strip + lower + Unicode alnum + whitespace; semantic mirror of DuckDB lower(strip_accents)+regexp_replace",
            "population": "complete train/test Source-1, no sampling",
            "int002_fit_selection": "sample517 md5 positions <=30000 plus 50001:200000 fit-fold only; fold517 sha256",
            "int002_fit_anchor_count": len(selected),
            "runtime_seconds": {"train_scan": train_seconds, "test_scan": test_seconds},
        },
        "row_counts": {"train": dict(train_rows), "test": dict(test_rows)},
        "population_features": {"train": {}, "test": {}},
        "int002_fit_features": {"global": {}, "by_country": {}},
        "comparisons": {"same_country_train_test": {}, "test_vs_int002_fit_global": {}},
    }
    for split, cs in [("train", train_c), ("test", test_c)]:
        for country, fields in cs.items():
            result["population_features"][split][country] = {
                field: hist_stats(counter) for field, counter in fields.items()
            }

    for field in ("name", "address"):
        result["int002_fit_features"]["global"][field] = hist_summary(fit_global[field])
    for country, data in fit_by_country.items():
        result["int002_fit_features"]["by_country"][country] = {
            "anchors": data["anchors"],
            "name": hist_summary(data["name"]),
            "address": hist_summary(data["address"]),
        }

    for country in sorted(set(train_c) & set(test_c)):
        result["comparisons"]["same_country_train_test"][country] = {}
        for field in ("name", "address"):
            tr = result["population_features"]["train"][country][field]
            te = result["population_features"]["test"][country][field]
            result["comparisons"]["same_country_train_test"][country][field] = {
                "weighted_ks_feature_frequency": weighted_ks(tr["feature_frequency_hist"], te["feature_frequency_hist"]),
                "mean_log1p_delta": te["mean_log1p_frequency"] - tr["mean_log1p_frequency"],
                "collision_rate_delta_pp": 100*(te["collision_row_rate_all"] - tr["collision_row_rate_all"]),
                "max_frequency_train": tr["max_frequency"],
                "max_frequency_test": te["max_frequency"],
            }

    for country in sorted(test_c):
        result["comparisons"]["test_vs_int002_fit_global"][country] = {}
        for field in ("name", "address"):
            te = result["population_features"]["test"][country][field]
            result["comparisons"]["test_vs_int002_fit_global"][country][field] = oos_vs_fit(
                te["feature_frequency_hist"], fit_global[field]
            )

    for split in ("train", "test"):
        for country in result["population_features"][split]:
            for field in ("name", "address"):
                result["population_features"][split][country][field].pop("feature_frequency_hist", None)
    for field in ("name", "address"):
        result["int002_fit_features"]["global"][field].pop("support_values", None)
    for country in result["int002_fit_features"]["by_country"]:
        for field in ("name", "address"):
            result["int002_fit_features"]["by_country"][country][field].pop("support_values", None)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
