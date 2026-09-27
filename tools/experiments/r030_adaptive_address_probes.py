"""R030: Source-1 proxy audit for wider/adaptive address-word probe budgets.

This is analysis-only. It uses country/split-local Source-1 document frequency as a
proxy for target posting pressure; production retrieval uses pooled S2+S3 target
frequency and therefore requires a separate full-target empirical gate.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ADDRESS_STOP = {
    "road", "street", "avenue", "drive", "lane", "floor", "near",
    "opposite", "the", "and", "unit", "plot", "no",
}
DF_CUTOFF = 1000
POLICIES = ("fixed4", "fixed6", "fixed8", "adaptive4to8_budget200")
ADAPTIVE_EXTRA_BUDGET = 200


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()
    out: list[str] = []
    last_space = True
    for ch in text:
        cat = unicodedata.category(ch)
        if cat and cat[0] in ("L", "N"):
            out.append(ch)
            last_space = False
        elif not last_space:
            out.append(" ")
            last_space = True
    return "".join(out).strip()


def address_words(address: str) -> set[str]:
    return {
        token
        for token in normalize(address).split()
        if len(token) >= 3 and not token.isdigit() and token not in ADDRESS_STOP
    }


def select_policy(
    eligible: list[tuple[int, str]],
    policy: str,
    *,
    extra_budget: int = ADAPTIVE_EXTRA_BUDGET,
) -> list[tuple[int, str]]:
    if policy.startswith("fixed"):
        k = int(policy.removeprefix("fixed"))
        return eligible[:k]
    if policy != "adaptive4to8_budget200":
        raise ValueError(f"unknown policy: {policy}")
    chosen = eligible[:4]
    extra_cost = 0
    for item in eligible[4:8]:
        if extra_cost + item[0] > extra_budget:
            break
        chosen.append(item)
        extra_cost += item[0]
    return chosen


def hist_quantile(hist: Counter[int], q: float) -> int | None:
    total = sum(hist.values())
    if not total:
        return None
    target = max(1, math.ceil(q * total))
    seen = 0
    for value, count in sorted(hist.items()):
        seen += count
        if seen >= target:
            return value
    raise AssertionError("unreachable")


def audit_split(path: Path) -> dict:
    started = time.time()
    dfs: dict[str, Counter[str]] = defaultdict(Counter)
    rows: Counter[str] = Counter()

    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            country = row.get("country", "")
            dfs[country].update(address_words(row.get("business_address", "") or ""))
            rows[country] += 1

    acc = {country: {policy: Counter() for policy in POLICIES} for country in dfs}
    eligible_hist = {country: Counter() for country in dfs}
    posting_hist = {
        country: {policy: Counter() for policy in POLICIES} for country in dfs
    }

    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            country = row.get("country", "")
            tokens = address_words(row.get("business_address", "") or "")
            eligible = sorted(
                (dfs[country][token], token)
                for token in tokens
                if dfs[country][token] <= DF_CUTOFF
            )
            eligible_hist[country][len(eligible)] += 1
            for policy in POLICIES:
                selected = select_policy(eligible, policy)
                a = acc[country][policy]
                a["eligible_keys"] += len(eligible)
                a["selected_keys"] += len(selected)
                posting_mass = sum(df for df, _ in selected)
                a["posting_mass"] += posting_mass
                posting_hist[country][policy][posting_mass] += 1
                if len(selected) > 4:
                    a["records_gt4"] += 1
                for df, _ in selected[4:]:
                    a["extra_keys_vs_fixed4"] += 1
                    a["extra_posting_mass"] += df
                    a["extra_keys_df_le_10"] += df <= 10
                    a["extra_keys_df_le_100"] += df <= 100

    out = {
        "source": str(path),
        "df_cutoff": DF_CUTOFF,
        "adaptive_extra_budget": ADAPTIVE_EXTRA_BUDGET,
        "countries": {},
        "runtime_seconds": time.time() - started,
    }
    for country in sorted(dfs):
        n = rows[country]
        country_out = {
            "records": n,
            "address_vocab": len(dfs[country]),
            "eligible_count_quantiles": {
                "p50": hist_quantile(eligible_hist[country], 0.50),
                "p90": hist_quantile(eligible_hist[country], 0.90),
                "p95": hist_quantile(eligible_hist[country], 0.95),
                "p99": hist_quantile(eligible_hist[country], 0.99),
                "max": max(eligible_hist[country], default=None),
            },
            "policies": {},
        }
        for policy in POLICIES:
            a = acc[country][policy]
            eligible = a["eligible_keys"]
            selected = a["selected_keys"]
            country_out["policies"][policy] = {
                "eligible_keys": eligible,
                "selected_keys": selected,
                "dropped_keys": eligible - selected,
                "dropped_key_rate": (eligible - selected) / eligible if eligible else 0.0,
                "retained_key_rate": selected / eligible if eligible else 0.0,
                "mean_probes_per_record": selected / n if n else 0.0,
                "records_gt4_rate": a["records_gt4"] / n if n else 0.0,
                "estimated_posting_mass": a["posting_mass"],
                "mean_estimated_posting_mass_per_record": a["posting_mass"] / n if n else 0.0,
                "posting_mass_p90": hist_quantile(posting_hist[country][policy], 0.90),
                "posting_mass_p99": hist_quantile(posting_hist[country][policy], 0.99),
                "extra_keys_vs_fixed4": a["extra_keys_vs_fixed4"],
                "extra_posting_mass": a["extra_posting_mass"],
                "extra_keys_df_le_10": a["extra_keys_df_le_10"],
                "extra_keys_df_le_100": a["extra_keys_df_le_100"],
            }
        out["countries"][country] = country_out
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train-source1", type=Path, required=True)
    p.add_argument("--test-source1", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = {
        "experiment_id": "R030",
        "warning": "Source-1 DF proxy only; not production S2+S3 retrieval frequency.",
        "train": audit_split(args.train_source1),
        "test": audit_split(args.test_source1),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
