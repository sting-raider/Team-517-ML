#!/usr/bin/env python3
"""Compare current INT003 fit-name-family exposure in local evaluation vs full test S1."""
from __future__ import annotations
import argparse, csv, json, time
from collections import Counter
from pathlib import Path

from tools.experiments.i037_name_family_split_audit import (
    assign_sets, keep_top_positions, normalize_name, quantiles,
)


def overlap_summary(rows, fit_name, fit_country_name, core_name, core_country_name):
    nonempty = [r for r in rows if r["name"]]
    name_seen = [r for r in nonempty if fit_name[r["name"]] > 0]
    country_seen = [r for r in nonempty if fit_country_name[(r["country"], r["name"])] > 0]
    core_country_seen = [r for r in nonempty if core_country_name[(r["country"], r["name"])] > 0]
    return {
        "anchors": len(rows),
        "nonempty_name_anchors": len(nonempty),
        "empty_name_anchors": len(rows) - len(nonempty),
        "name_only_fit_family_overlap_anchors": len(name_seen),
        "name_only_fit_family_overlap_rate": len(name_seen) / len(nonempty) if nonempty else None,
        "same_country_fit_family_overlap_anchors": len(country_seen),
        "same_country_fit_family_overlap_rate": len(country_seen) / len(nonempty) if nonempty else None,
        "same_country_core_fit_family_overlap_anchors": len(core_country_seen),
        "same_country_core_fit_family_overlap_rate": len(core_country_seen) / len(nonempty) if nonempty else None,
        "incremental_same_country_overlap_from_expanded_fit": (len(country_seen) - len(core_country_seen)) / len(nonempty) if nonempty else None,
        "same_country_family_novel_anchors": len(nonempty) - len(country_seen),
        "fit_family_fanout_for_same_country_overlaps": quantiles([
            fit_country_name[(r["country"], r["name"])] for r in country_seen
        ]),
        "fit_family_fanout_for_name_only_overlaps": quantiles([
            fit_name[r["name"]] for r in name_seen
        ]),
    }


def scan_test(path: Path, fit_name, fit_country_name, core_name, core_country_name):
    started = time.time()
    totals = Counter()
    empty = Counter()
    name_seen = Counter()
    country_seen = Counter()
    core_country_seen = Counter()
    country_fanouts = {c: [] for c in ("US", "India", "France")}
    name_fanouts = {c: [] for c in ("US", "India", "France")}
    with path.open("r", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f, delimiter="\t")
        for row in rd:
            country = row["country"]
            name = normalize_name(row.get("business_name") or "")
            totals[country] += 1
            if not name:
                empty[country] += 1
                continue
            name_fanout = fit_name[name]
            country_fanout = fit_country_name[(country, name)]
            core_country_fanout = core_country_name[(country, name)]
            if name_fanout:
                name_seen[country] += 1
                name_fanouts.setdefault(country, []).append(name_fanout)
            if country_fanout:
                country_seen[country] += 1
                country_fanouts.setdefault(country, []).append(country_fanout)
            if core_country_fanout:
                core_country_seen[country] += 1

    out = {}
    for country in sorted(totals):
        denom = totals[country] - empty[country]
        out[country] = {
            "anchors": totals[country],
            "nonempty_name_anchors": denom,
            "empty_name_anchors": empty[country],
            "name_only_fit_family_overlap_anchors": name_seen[country],
            "name_only_fit_family_overlap_rate": name_seen[country] / denom if denom else None,
            "same_country_fit_family_overlap_anchors": country_seen[country],
            "same_country_fit_family_overlap_rate": country_seen[country] / denom if denom else None,
            "same_country_core_fit_family_overlap_anchors": core_country_seen[country],
            "same_country_core_fit_family_overlap_rate": core_country_seen[country] / denom if denom else None,
            "incremental_same_country_overlap_from_expanded_fit": (country_seen[country] - core_country_seen[country]) / denom if denom else None,
            "same_country_family_novel_anchors": denom - country_seen[country],
            "fit_family_fanout_for_same_country_overlaps": quantiles(country_fanouts.get(country, [])),
            "fit_family_fanout_for_name_only_overlaps": quantiles(name_fanouts.get(country, [])),
        }

    all_rows = sum(totals.values())
    all_empty = sum(empty.values())
    denom = all_rows - all_empty
    out["all"] = {
        "anchors": all_rows,
        "nonempty_name_anchors": denom,
        "empty_name_anchors": all_empty,
        "name_only_fit_family_overlap_anchors": sum(name_seen.values()),
        "name_only_fit_family_overlap_rate": sum(name_seen.values()) / denom if denom else None,
        "same_country_fit_family_overlap_anchors": sum(country_seen.values()),
        "same_country_fit_family_overlap_rate": sum(country_seen.values()) / denom if denom else None,
        "same_country_core_fit_family_overlap_anchors": sum(core_country_seen.values()),
        "same_country_core_fit_family_overlap_rate": sum(core_country_seen.values()) / denom if denom else None,
        "incremental_same_country_overlap_from_expanded_fit": (sum(country_seen.values()) - sum(core_country_seen.values())) / denom if denom else None,
        "same_country_family_novel_anchors": denom - sum(country_seen.values()),
    }
    return out, time.time() - started


def audit(train_source1: Path, test_source1: Path):
    started = time.time()
    chosen, train_scan = keep_top_positions(train_source1)
    sets = assign_sets(chosen)
    fit = sets["fit"]
    core = sets["fit_core"]
    fit_name = Counter(r["name"] for r in fit if r["name"])
    fit_country = Counter((r["country"], r["name"]) for r in fit if r["name"])
    core_name = Counter(r["name"] for r in core if r["name"])
    core_country = Counter((r["country"], r["name"]) for r in core if r["name"])

    def local_summary(rows):
        out = {"all": overlap_summary(rows, fit_name, fit_country, core_name, core_country)}
        for country in sorted({r["country"] for r in rows}):
            out[country] = overlap_summary(
                [r for r in rows if r["country"] == country],
                fit_name,
                fit_country,
                core_name,
                core_country,
            )
        return out

    local = {
        key: local_summary(rows)
        for key, rows in sets.items()
        if key in {"early", "calibrate", "holdout", "confirmation"}
    }
    test, test_seconds = scan_test(
        test_source1,
        fit_name,
        fit_country,
        core_name,
        core_country,
    )
    for country, expected in {"US": 663106, "India": 809986, "France": 259452}.items():
        if test[country]["anchors"] != expected:
            raise AssertionError(
                f"test {country} parity failed: {test[country]['anchors']} != {expected}"
            )
    if len(fit) != 108115:
        raise AssertionError(f"fit parity failed: {len(fit)} != 108115")

    return {
        "experiment": "X016",
        "scope": {
            "sampling": "none",
            "train_source1_rows": train_scan["source1_rows"],
            "test_source1_rows": test["all"]["anchors"],
            "fit_anchors": len(fit),
            "core_fit_anchors": len(core),
        },
        "local_evaluation": local,
        "test": test,
        "comparison": {
            "confirmation_minus_test_same_country_overlap_pp": {
                country: 100 * (
                    local["confirmation"][country]["same_country_fit_family_overlap_rate"]
                    - test[country]["same_country_fit_family_overlap_rate"]
                )
                for country in ("US", "India")
            },
            "holdout_minus_test_same_country_overlap_pp": {
                country: 100 * (
                    local["holdout"][country]["same_country_fit_family_overlap_rate"]
                    - test[country]["same_country_fit_family_overlap_rate"]
                )
                for country in ("US", "India")
            },
        },
        "runtime": {
            "train_scan_seconds": train_scan["seconds"],
            "test_scan_seconds": test_seconds,
            "total_seconds": time.time() - started,
        },
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--train-source1", type=Path, required=True)
    p.add_argument("--test-source1", type=Path, required=True)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    result = audit(a.train_source1, a.test_source1)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
