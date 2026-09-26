"""M001a: full-Source-1 IDF-weighted token-overlap feasibility audit.

This is a forensic/feature-behavior helper only. It does not read match labels,
target-source records, or use entity IDs as predictive evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
import unicodedata
from array import array
from collections import Counter
from pathlib import Path

import numpy as np


def normalize(text: str) -> str:
    """Semantic mirror of lower(strip_accents()) + non-letter/number collapse."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()
    out: list[str] = []
    last_space = True
    for ch in text:
        category = unicodedata.category(ch)
        if category and category[0] in ("L", "N"):
            out.append(ch)
            last_space = False
        elif not last_space:
            out.append(" ")
            last_space = True
    return "".join(out).strip()


def token_set(text: str) -> set[str]:
    return set(normalize(text).split())


def idf_weight(rows: int, df: int) -> float:
    if rows < 0 or df < 0 or df > rows:
        raise ValueError("invalid rows/df")
    return math.log((rows + 1.0) / (df + 1.0)) + 1.0


def weighted_overlap(
    left: set[str], right: set[str], weights: dict[str, float], default_weight: float = 1.0
) -> tuple[float, float, float, float]:
    """Weighted analog of Jaccard, overlap, left coverage, right coverage."""
    left, right = set(left), set(right)
    inter, union = left & right, left | right

    def mass(values: set[str]) -> float:
        total = 0.0
        for token in values:
            weight = float(weights.get(token, default_weight))
            if not math.isfinite(weight) or weight <= 0:
                raise ValueError("token weights must be finite and positive")
            total += weight
        return total

    if not union:
        return 0.0, 0.0, 0.0, 0.0
    wi, wu, wl, wr = mass(inter), mass(union), mass(left), mass(right)
    jaccard = wi / wu if wu else 0.0
    overlap = wi / min(wl, wr) if min(wl, wr) > 0 else 0.0
    left_coverage = wi / wl if wl > 0 else 0.0
    right_coverage = wi / wr if wr > 0 else 0.0
    return jaccard, overlap, left_coverage, right_coverage


def census(path: Path, country: str) -> dict:
    started = time.time()
    rows = 0
    name_df: Counter[str] = Counter()
    address_df: Counter[str] = Counter()
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row.get("country", "") != country:
                continue
            rows += 1
            name_df.update(token_set(row.get("business_name", "") or ""))
            address_df.update(token_set(row.get("business_address", "") or ""))
    return {
        "country": country,
        "rows": rows,
        "name": name_df,
        "address": address_df,
        "seconds": time.time() - started,
    }


def _quantiles(values: array, points=(.1, .25, .5, .75, .9, .95, .99)) -> dict:
    if not values:
        return {}
    x = np.frombuffer(values, dtype=np.float64)
    return {str(q): float(np.quantile(x, q)) for q in points}


def probe(path: Path, profile: dict) -> dict:
    """Delete one rare/common token per eligible row and compare score sensitivity."""
    country = profile["country"]
    n = profile["rows"]
    started = time.time()
    acc = {
        field: {
            "rows": 0,
            "eligible": 0,
            "nonuniform": 0,
            "gap": array("d"),
            "rare_df": array("d"),
            "common_df": array("d"),
            "rare_share_sum": 0.0,
            "common_share_sum": 0.0,
            "unweighted_gap_max_abs": 0.0,
        }
        for field in ("name", "address")
    }

    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row.get("country", "") != country:
                continue
            for field, column in (
                ("name", "business_name"),
                ("address", "business_address"),
            ):
                d = acc[field]
                d["rows"] += 1
                tokens = token_set(row.get(column, "") or "")
                if len(tokens) < 2:
                    continue
                d["eligible"] += 1
                dfs: Counter[str] = profile[field]
                rare = min(tokens, key=lambda token: (dfs[token], token))
                common = max(tokens, key=lambda token: (dfs[token], token))
                if dfs[rare] != dfs[common]:
                    d["nonuniform"] += 1
                weights = {token: idf_weight(n, dfs[token]) for token in tokens}
                total = sum(weights.values())
                rare_score = (total - weights[rare]) / total
                common_score = (total - weights[common]) / total
                gap = common_score - rare_score
                d["gap"].append(gap)
                d["rare_df"].append(float(dfs[rare]))
                d["common_df"].append(float(dfs[common]))
                d["rare_share_sum"] += 1.0 - rare_score
                d["common_share_sum"] += 1.0 - common_score

                # The unweighted set Jaccard is identical because both probes
                # delete exactly one token from the same original set.
                k = len(tokens)
                unweighted_rare = (k - 1) / k
                unweighted_common = (k - 1) / k
                d["unweighted_gap_max_abs"] = max(
                    d["unweighted_gap_max_abs"],
                    abs(unweighted_common - unweighted_rare),
                )

    fields = {}
    for field, d in acc.items():
        gaps = np.frombuffer(d["gap"], dtype=np.float64)
        eligible = d["eligible"]
        fields[field] = {
            "rows": d["rows"],
            "eligible": eligible,
            "eligible_rate": eligible / d["rows"] if d["rows"] else 0.0,
            "nonuniform": d["nonuniform"],
            "nonuniform_rate_of_eligible": d["nonuniform"] / eligible if eligible else 0.0,
            "gap_mean": float(gaps.mean()) if eligible else 0.0,
            "gap_quantiles": _quantiles(d["gap"]),
            "gap_ge_0.02": float(np.mean(gaps >= .02)) if eligible else 0.0,
            "gap_ge_0.05": float(np.mean(gaps >= .05)) if eligible else 0.0,
            "gap_ge_0.10": float(np.mean(gaps >= .10)) if eligible else 0.0,
            "rare_df_quantiles": _quantiles(d["rare_df"], (.1, .5, .9)),
            "common_df_quantiles": _quantiles(d["common_df"], (.1, .5, .9)),
            "mean_rare_token_weight_share": d["rare_share_sum"] / eligible if eligible else 0.0,
            "mean_common_token_weight_share": d["common_share_sum"] / eligible if eligible else 0.0,
            "unweighted_gap_max_abs": d["unweighted_gap_max_abs"],
        }
    return {"country": country, "fields": fields, "seconds": time.time() - started}


def audit(path: Path, countries=("US", "India")) -> dict:
    profiles = {}
    census_seconds = 0.0
    for country in countries:
        profile = census(path, country)
        profiles[country] = profile
        census_seconds += profile["seconds"]

    probes = {}
    probe_seconds = 0.0
    population = {}
    for country in countries:
        profile = profiles[country]
        measured = probe(path, profile)
        probes[country] = measured["fields"]
        probe_seconds += measured["seconds"]
        population[country] = {
            "rows": profile["rows"],
            "name_vocab": len(profile["name"]),
            "address_vocab": len(profile["address"]),
            "name_postings": sum(profile["name"].values()),
            "address_postings": sum(profile["address"].values()),
        }

    return {
        "experiment_id": "M001a",
        "status": "PROMOTE-EMPIRICAL-GATE",
        "idf_formula": "log((N_country+1)/(df_country_field(token)+1))+1",
        "token_semantics": "production-normalized whitespace token sets; all tokens including numbers",
        "population": population,
        "probe": probes,
        "runtime_seconds": {
            "census": census_seconds,
            "probe": probe_seconds,
            "total": census_seconds + probe_seconds,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source1", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.source1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
