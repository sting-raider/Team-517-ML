#!/usr/bin/env python3
"""Audit normalized-name family dependence across INT003 Source-1 splits.

Full-population streaming helper. Uses only Source-1 + supplied truth.
"""
from __future__ import annotations
import argparse, csv, hashlib, heapq, json, math, time, unicodedata
from collections import Counter
from pathlib import Path


def normalize_name(value: str) -> str:
    """Mirror X002's production-style folded name normalization.

    lower -> NFD -> remove combining marks -> retain Unicode Letter/Number -> collapse separators.
    X002 measured zero train-US/India business-name key change/collision difference vs the
    folded production semantics, which is the population used here.
    """
    text = unicodedata.normalize("NFD", (value or "").lower())
    out: list[str] = []
    pending_space = False
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("M"):
            continue
        if cat[:1] in {"L", "N"}:
            if pending_space and out:
                out.append(" ")
            out.append(ch)
            pending_space = False
        elif out:
            pending_space = True
    return "".join(out).strip()


def fold(entity_id: str) -> str:
    bucket = int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100
    return "fit" if bucket < 60 else "early" if bucket < 75 else "calibrate" if bucket < 90 else "holdout"


def sample_key(entity_id: str) -> int:
    return int.from_bytes(hashlib.md5(("sample517:" + entity_id).encode()).digest(), "big")


def keep_top_positions(source1: Path, limit: int = 200_000):
    heap = []
    rows = 0
    countries = Counter()
    empty_names = Counter()
    started = time.time()
    with source1.open("r", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {"entity_id", "business_name", "country"}
        if not required.issubset(rd.fieldnames or []):
            raise ValueError(f"missing Source-1 columns: {required - set(rd.fieldnames or [])}")
        for row in rd:
            rows += 1
            eid = row["entity_id"]
            country = row["country"]
            name = normalize_name(row.get("business_name") or "")
            countries[country] += 1
            if not name:
                empty_names[country] += 1
            key = sample_key(eid)
            item = (-key, eid, country, name)
            if len(heap) < limit:
                heapq.heappush(heap, item)
            elif key < -heap[0][0]:
                heapq.heapreplace(heap, item)
    chosen = [(-neg, eid, country, name) for neg, eid, country, name in heap]
    chosen.sort(key=lambda x: x[0])
    if len(chosen) != min(limit, rows):
        raise AssertionError("top-position population size mismatch")
    return chosen, {
        "source1_rows": rows,
        "country_rows": dict(sorted(countries.items())),
        "empty_normalized_name_rows": dict(sorted(empty_names.items())),
        "seconds": time.time() - started,
    }


def assign_sets(chosen):
    sets = {k: [] for k in ("fit", "fit_core", "fit_expanded_extra", "early", "calibrate", "holdout", "confirmation")}
    for pos, (_, eid, country, name) in enumerate(chosen, 1):
        f = fold(eid)
        record = {"id": eid, "country": country, "name": name, "position": pos, "fold": f}
        if pos <= 30_000:
            sets[f].append(record)
            if f == "fit":
                sets["fit_core"].append(record)
        elif 45_001 <= pos <= 50_000:
            sets["confirmation"].append(record)
        elif 50_001 <= pos <= 200_000 and f == "fit":
            sets["fit"].append(record)
            sets["fit_expanded_extra"].append(record)
    return sets


def load_truth_cardinality(path: Path, wanted: set[str]):
    out = {}
    rows = 0
    started = time.time()
    with path.open("r", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f, delimiter="\t")
        for row in rd:
            rows += 1
            eid = row["source1_entity_id"]
            if eid in wanted:
                matches = (row.get("matched_entity_ids") or "").strip()
                out[eid] = 0 if not matches else matches.count(",") + 1
    missing = wanted - out.keys()
    if missing:
        raise ValueError(f"truth missing {len(missing)} selected anchors")
    return out, {"truth_rows_scanned": rows, "seconds": time.time() - started}


def quantiles(values):
    if not values:
        return {"p50": 0, "p90": 0, "p99": 0, "max": 0}
    v = sorted(values)

    def q(p):
        idx = max(0, min(len(v) - 1, math.ceil(p * len(v)) - 1))
        return int(v[idx])

    return {"p50": q(.5), "p90": q(.9), "p99": q(.99), "max": int(v[-1])}


def summarize(rows, truth, fit_name_counts, fit_country_name_counts, core_name_counts, core_country_name_counts):
    def one(part):
        total = len(part)
        nonempty = [r for r in part if r["name"]]
        overlap_name = [r for r in nonempty if fit_name_counts[r["name"]] > 0]
        overlap_country = [r for r in nonempty if fit_country_name_counts[(r["country"], r["name"])] > 0]
        novel_country = [r for r in nonempty if fit_country_name_counts[(r["country"], r["name"])] == 0]
        overlap_core_country = [r for r in nonempty if core_country_name_counts[(r["country"], r["name"])] > 0]

        def card_stats(group):
            cards = [truth[r["id"]] for r in group]
            return {
                "anchors": len(group),
                "mean_truth_cardinality": sum(cards) / len(cards) if cards else None,
                "singleton_rate": sum(c == 0 for c in cards) / len(cards) if cards else None,
                "high_cardinality_ge5_rate": sum(c >= 5 for c in cards) / len(cards) if cards else None,
            }

        return {
            "anchors": total,
            "nonempty_name_anchors": len(nonempty),
            "empty_name_anchors": total - len(nonempty),
            "name_family_seen_in_fit_anchors": len(overlap_name),
            "name_family_seen_in_fit_rate_nonempty": len(overlap_name) / len(nonempty) if nonempty else None,
            "same_country_name_family_seen_in_fit_anchors": len(overlap_country),
            "same_country_name_family_seen_in_fit_rate_nonempty": len(overlap_country) / len(nonempty) if nonempty else None,
            "same_country_name_family_seen_in_core_fit_anchors": len(overlap_core_country),
            "same_country_name_family_seen_in_core_fit_rate_nonempty": len(overlap_core_country) / len(nonempty) if nonempty else None,
            "incremental_overlap_rate_from_expanded_fit": (len(overlap_country) - len(overlap_core_country)) / len(nonempty) if nonempty else None,
            "family_novel_same_country_anchors": len(novel_country),
            "fit_family_fanout_for_same_country_overlaps": quantiles([
                fit_country_name_counts[(r["country"], r["name"])] for r in overlap_country
            ]),
            "truth_composition": card_stats(part),
            "truth_composition_same_country_family_overlap": card_stats(overlap_country),
            "truth_composition_same_country_family_novel": card_stats(novel_country),
        }

    result = {"all": one(rows)}
    for country in sorted({r["country"] for r in rows}):
        result[country] = one([r for r in rows if r["country"] == country])
    return result


def audit(source1: Path, truth_path: Path):
    started = time.time()
    chosen, scan = keep_top_positions(source1)
    sets = assign_sets(chosen)
    fit = sets["fit"]
    core_fit = sets["fit_core"]
    fit_name_counts = Counter(r["name"] for r in fit if r["name"])
    fit_country_name_counts = Counter((r["country"], r["name"]) for r in fit if r["name"])
    core_name_counts = Counter(r["name"] for r in core_fit if r["name"])
    core_country_name_counts = Counter((r["country"], r["name"]) for r in core_fit if r["name"])
    wanted = {
        r["id"]
        for k, rows in sets.items()
        if k not in {"fit_core", "fit_expanded_extra"}
        for r in rows
    }
    truth, truth_scan = load_truth_cardinality(truth_path, wanted)

    split_counts = {k: len(v) for k, v in sets.items()}
    if split_counts["fit"] != 108_115:
        raise AssertionError(f"INT003 fit anchor parity failed: {split_counts['fit']} != 108115")
    if split_counts["calibrate"] != 4_389:
        raise AssertionError(f"calibration parity failed: {split_counts['calibrate']} != 4389")
    if split_counts["holdout"] != 3_051:
        raise AssertionError(f"holdout parity failed: {split_counts['holdout']} != 3051")
    if split_counts["confirmation"] != 5_000:
        raise AssertionError(f"confirmation parity failed: {split_counts['confirmation']} != 5000")

    result = {
        "experiment": "I037",
        "scope": {
            "sampling": "none",
            "source1_rows": scan["source1_rows"],
            "hash_positions_reconstructed": 200_000,
            "split_counts": split_counts,
            "country_rows": scan["country_rows"],
        },
        "normalization": {
            "family_key": "lower + NFD combining-mark removal + Unicode letters/numbers + separator collapse",
            "parity_basis": "X002 found zero train-US/India business-name changed-rate and zero collision inflation between its NFD folded mirror and production folded semantics",
            "empty_names_excluded_from_family-overlap denominators": True,
        },
        "fit_families": {
            "fit_anchors": len(fit),
            "core_fit_anchors": len(core_fit),
            "expanded_extra_fit_anchors": len(sets["fit_expanded_extra"]),
            "distinct_nonempty_name_families": len(fit_name_counts),
            "core_distinct_nonempty_name_families": len(core_name_counts),
            "distinct_nonempty_country_name_families": len(fit_country_name_counts),
            "anchors_in_repeated_name_families": sum(c for c in fit_name_counts.values() if c > 1),
            "anchors_in_repeated_country_name_families": sum(c for c in fit_country_name_counts.values() if c > 1),
        },
        "evaluation": {
            k: summarize(
                v,
                truth,
                fit_name_counts,
                fit_country_name_counts,
                core_name_counts,
                core_country_name_counts,
            )
            for k, v in sets.items()
            if k in {"early", "calibrate", "holdout", "confirmation"}
        },
        "runtime": {
            "source1_scan_seconds": scan["seconds"],
            "truth_scan_seconds": truth_scan["seconds"],
            "total_seconds": time.time() - started,
        },
    }
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source1", type=Path, required=True)
    p.add_argument("--truth", type=Path, required=True)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    result = audit(a.source1, a.truth)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
