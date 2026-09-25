"""Aggregate-only audit of truth-set cardinality and source multiplicity."""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import os
import time
from collections import Counter, defaultdict
from pathlib import Path


def fold(entity_id: str) -> str:
    bucket = int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100
    return "fit" if bucket < 60 else "early" if bucket < 75 else "calibrate" if bucket < 90 else "holdout"


def match_counts(matches: str) -> tuple[int, int, int]:
    ids = [x.strip() for x in matches.split(",") if x.strip()] if matches else []
    s2 = sum(x.startswith("S2-") for x in ids)
    s3 = sum(x.startswith("S3-") for x in ids)
    return s2, s3, len(ids)


def best_case_f05(true_size: int, predicted_size: int) -> float:
    if true_size == 0:
        return float(predicted_size == 0)
    tp = min(true_size, predicted_size)
    if not tp:
        return 0.0
    fp = max(0, predicted_size - true_size)
    fn = max(0, true_size - predicted_size)
    return 1.25 * tp / (1.25 * tp + fp + 0.25 * fn)


def _quantiles(counter: Counter, qs=(0, .5, .9, .95, .99, .999, 1)):
    n = sum(counter.values())
    if not n:
        return {str(q): None for q in qs}
    items = sorted(counter.items())
    targets = [max(1, math.ceil(q * n)) if q > 0 else 1 for q in qs]
    out = {}
    cumulative = 0
    qi = 0
    for value, count in items:
        cumulative += count
        while qi < len(qs) and cumulative >= targets[qi]:
            out[str(qs[qi])] = value
            qi += 1
    return out


def _corr(n, sx, sy, sxx, syy, sxy):
    num = n * sxy - sx * sy
    dx = n * sxx - sx * sx
    dy = n * syy - sy * sy
    return num / math.sqrt(dx * dy) if dx > 0 and dy > 0 else None


def _summary(n, card, s2, s3, composition, sums):
    non_singletons = n - card.get(0, 0)
    return {
        "anchors": n,
        "singleton_count": card.get(0, 0),
        "singleton_rate": card.get(0, 0) / n if n else None,
        "non_singleton_count": non_singletons,
        "mean_total_matches": sum(k * v for k, v in card.items()) / n if n else None,
        "mean_s2_matches": sums["sum_s2"] / n if n else None,
        "mean_s3_matches": sums["sum_s3"] / n if n else None,
        "cardinality_counts": dict(sorted(card.items())),
        "cardinality_quantiles": _quantiles(card),
        "s2_count_counts": dict(sorted(s2.items())),
        "s3_count_counts": dict(sorted(s3.items())),
        "s2_count_quantiles": _quantiles(s2),
        "s3_count_quantiles": _quantiles(s3),
        "composition_counts": dict(composition),
        "composition_rates": {k: v / n for k, v in composition.items()} if n else {},
        "tail_rates": {f"ge_{k}": sum(v for x, v in card.items() if x >= k) / n for k in (2, 3, 5, 10, 20, 50, 100)} if n else {},
        "s2_s3_count_pearson": _corr(n, sums["sum_s2"], sums["sum_s3"], sums["sum_s2sq"], sums["sum_s3sq"], sums["sum_cross"]),
    }


def audit(source1: Path, truth: Path, sample_size: int = 30000) -> dict:
    started = time.time()
    country_by_id = {}
    country_counts = Counter()
    heap = []
    with source1.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            eid, country = row["entity_id"], row["country"]
            country_by_id[eid] = country
            country_counts[country] += 1
            h = int(hashlib.md5(("sample517:" + eid).encode()).hexdigest(), 16)
            item = (-h, eid)
            if len(heap) < sample_size:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
    sample_ids = {eid for _, eid in heap}
    sample_folds = {eid: fold(eid) for eid in sample_ids}

    global_card, global_s2, global_s3, global_comp = Counter(), Counter(), Counter(), Counter()
    by_country = defaultdict(lambda: {"anchors": 0, "card": Counter(), "s2": Counter(), "s3": Counter(), "comp": Counter(), "sum_s2": 0, "sum_s3": 0, "sum_s2sq": 0, "sum_s3sq": 0, "sum_cross": 0})
    folds = defaultdict(lambda: {"anchors": 0, "card": Counter(), "comp": Counter(), "country": Counter(), "sum_total": 0})
    truth_ids = set()
    duplicate_target_ids = 0
    bad_prefixes = Counter()
    total_edges = 0
    sums = {"sum_s2": 0, "sum_s3": 0, "sum_s2sq": 0, "sum_s3sq": 0, "sum_cross": 0}
    truth_rows = 0

    with truth.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            truth_rows += 1
            aid = row["source1_entity_id"]
            raw = row["matched_entity_ids"] or ""
            truth_ids.add(aid)
            ids = [x.strip() for x in raw.split(",") if x.strip()] if raw else []
            duplicate_target_ids += len(ids) - len(set(ids))
            s2 = sum(target.startswith("S2-") for target in ids)
            s3 = sum(target.startswith("S3-") for target in ids)
            total = len(ids)
            for target in ids:
                if not (target.startswith("S2-") or target.startswith("S3-")):
                    bad_prefixes[target.split("-", 1)[0] if "-" in target else target] += 1
            composition = "singleton" if total == 0 else "both" if s2 and s3 else "s2_only" if s2 else "s3_only" if s3 else "other"
            country = country_by_id.get(aid, "__UNKNOWN__")
            total_edges += total
            global_card[total] += 1; global_s2[s2] += 1; global_s3[s3] += 1; global_comp[composition] += 1
            bc = by_country[country]
            bc["anchors"] += 1; bc["card"][total] += 1; bc["s2"][s2] += 1; bc["s3"][s3] += 1; bc["comp"][composition] += 1
            for target_sums in (bc, sums):
                target_sums["sum_s2"] += s2; target_sums["sum_s3"] += s3
                target_sums["sum_s2sq"] += s2 * s2; target_sums["sum_s3sq"] += s3 * s3; target_sums["sum_cross"] += s2 * s3
            if aid in sample_ids:
                fs = folds[sample_folds[aid]]
                fs["anchors"] += 1; fs["card"][total] += 1; fs["comp"][composition] += 1; fs["country"][country] += 1; fs["sum_total"] += total

    report = {
        "protocol": {
            "source1_bytes": os.path.getsize(source1), "truth_bytes": os.path.getsize(truth),
            "sample": f"{sample_size:,} smallest md5(sample517:<entity_id>)",
            "fold": "sha256(fold517:<entity_id>) first8 mod100; 60/15/15/10",
        },
        "integrity": {
            "source1_rows": len(country_by_id), "truth_rows": truth_rows, "distinct_truth_anchors": len(truth_ids),
            "missing_truth_anchors": len(set(country_by_id) - truth_ids), "unknown_truth_anchors": len(truth_ids - set(country_by_id)),
            "duplicate_truth_anchor_rows": truth_rows - len(truth_ids), "duplicate_target_ids_within_truth_rows": duplicate_target_ids,
            "bad_target_prefix_counts": dict(bad_prefixes), "total_positive_edges": total_edges, "source1_country_counts": dict(country_counts),
        },
        "overall": _summary(truth_rows, global_card, global_s2, global_s3, global_comp, sums),
        "by_country": {},
        "development_sample": {"sample_size": len(sample_ids), "folds": {}},
        "metric_cardinality_sensitivity": {
            "best_case_score_by_true_and_predicted_set_size": {str(m): {str(p): best_case_f05(m, p) for p in range(0, min(10, m + 4) + 1)} for m in range(8)},
            "one_extra_false_positive_penalty": {str(m): 1 - best_case_f05(m, m + 1) for m in range(1, 8)},
            "one_missing_true_penalty": {str(m): 1 - best_case_f05(m, m - 1) for m in range(1, 8)},
        },
    }
    for country, bc in sorted(by_country.items()):
        report["by_country"][country] = _summary(bc["anchors"], bc["card"], bc["s2"], bc["s3"], bc["comp"], bc)
    full_singleton = report["overall"]["singleton_rate"]
    full_mean = report["overall"]["mean_total_matches"]
    for name in ("fit", "early", "calibrate", "holdout"):
        fs = folds[name]; n = fs["anchors"]
        item = {
            "anchors": n, "country_counts": dict(fs["country"]), "cardinality_counts": dict(sorted(fs["card"].items())),
            "composition_counts": dict(fs["comp"]), "composition_rates": {k: v / n for k, v in fs["comp"].items()} if n else {},
            "singleton_count": fs["card"].get(0, 0), "singleton_rate": fs["card"].get(0, 0) / n if n else None,
            "mean_total_matches": fs["sum_total"] / n if n else None,
        }
        item["singleton_rate_delta_vs_full"] = item["singleton_rate"] - full_singleton
        item["mean_matches_delta_vs_full"] = item["mean_total_matches"] - full_mean
        report["development_sample"]["folds"][name] = item
    report["runtime_seconds"] = time.time() - started
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source1", type=Path, required=True)
    p.add_argument("--truth", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--sample-size", type=int, default=30000)
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args()
    result = audit(a.source1, a.truth, a.sample_size)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    if not a.quiet:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps({"runtime_seconds": result["runtime_seconds"], "integrity": result["integrity"]}, sort_keys=True))


if __name__ == "__main__":
    main()
