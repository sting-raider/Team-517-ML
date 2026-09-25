"""Full Source-1 same-address hard-negative audit with bounded memory.

Uses only supplied challenge fields. Entity IDs are intentionally discarded before
analysis and are never used as evidence.
"""
from __future__ import annotations

import argparse
import csv
import heapq
import itertools
import json
import math
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def normalize_repo_like(value: str | None) -> str:
    """Mirror lowercase/accent-strip/letters+digits normalization."""
    value = (value or "").lower()
    value = "".join(
        ch for ch in unicodedata.normalize("NFD", value)
        if unicodedata.category(ch) != "Mn"
    )
    out: list[str] = []
    previous_separator = True
    for ch in value:
        category = unicodedata.category(ch)
        if category and category[0] in {"L", "N"}:
            out.append(ch)
            previous_separator = False
        elif not previous_separator:
            out.append(" ")
            previous_separator = True
    return "".join(out).strip()


def choose2(n: int) -> int:
    return n * (n - 1) // 2


def nearest_rank_quantiles(values: list[int]) -> dict[str, int | None]:
    if not values:
        return {"p50": None, "p90": None, "p99": None, "max": None}
    values = sorted(values)

    def q(p: float) -> int:
        return values[max(0, min(len(values) - 1, math.ceil(p * len(values)) - 1))]

    return {"p50": q(.50), "p90": q(.90), "p99": q(.99), "max": values[-1]}


def group_size_bucket(n: int) -> str:
    if n == 2:
        return "2"
    if n <= 5:
        return "3-5"
    if n <= 10:
        return "6-10"
    if n <= 50:
        return "11-50"
    return "51+"


def token_count_bucket(n: int) -> str:
    if n <= 2:
        return "1-2"
    if n <= 5:
        return "3-5"
    if n <= 10:
        return "6-10"
    return "11+"


def text_length_bucket(n: int) -> str:
    if n <= 10:
        return "<=10"
    if n <= 25:
        return "11-25"
    if n <= 50:
        return "26-50"
    return "51+"


def jaccard_bucket(value: float) -> str:
    if value == 0:
        return "0"
    if value <= .25:
        return "(0,.25]"
    if value <= .50:
        return "(.25,.5]"
    if value <= .75:
        return "(.5,.75]"
    if value < 1:
        return "(.75,1)"
    return "1"


def _new_stats() -> dict:
    return {
        "records": 0,
        "empty_address_records": 0,
        "unique_nonempty_addresses": 0,
        "collision_groups": 0,
        "collision_records": 0,
        "collision_pairs": 0,
        "same_name_only_collision_groups": 0,
        "hard_negative_like_groups": 0,
        "hard_negative_like_records": 0,
        "cross_name_pairs": 0,
        "same_name_pairs_within_collisions": 0,
        "hard_groups_with_empty_name": 0,
        "collision_group_sizes": [],
        "hard_group_sizes": [],
        "hard_distinct_name_counts": [],
        "collision_group_size_hist": Counter(),
        "hard_group_size_hist": Counter(),
        "hard_group_token_hist": Counter(),
        "hard_group_length_hist": Counter(),
        "hard_group_digit_hist": Counter(),
        "hard_pair_token_jaccard_bins": Counter(),
        "hard_pair_mass_by_group_size": Counter(),
        "hard_pairs_shared_any_name_token": 0,
        "hard_pairs_zero_name_token_overlap": 0,
        "hard_pairs_compact_prefix6_equal": 0,
    }


def _update_group(stats: dict, address: str, names: list[str]) -> None:
    n = len(names)
    stats["records"] += n
    if not address:
        stats["empty_address_records"] += n
        return
    stats["unique_nonempty_addresses"] += 1
    if n < 2:
        return

    name_counts = Counter(names)
    distinct_names = len(name_counts)
    total_pairs = choose2(n)
    same_name_pairs = sum(choose2(c) for c in name_counts.values())
    cross_name_pairs = total_pairs - same_name_pairs
    size_bucket = group_size_bucket(n)

    stats["collision_groups"] += 1
    stats["collision_records"] += n
    stats["collision_pairs"] += total_pairs
    stats["same_name_pairs_within_collisions"] += same_name_pairs
    stats["collision_group_sizes"].append(n)
    stats["collision_group_size_hist"][size_bucket] += 1

    if distinct_names == 1:
        stats["same_name_only_collision_groups"] += 1
        return

    stats["hard_negative_like_groups"] += 1
    stats["hard_negative_like_records"] += n
    stats["cross_name_pairs"] += cross_name_pairs
    stats["hard_group_sizes"].append(n)
    stats["hard_distinct_name_counts"].append(distinct_names)
    stats["hard_group_size_hist"][size_bucket] += 1
    stats["hard_group_token_hist"][token_count_bucket(len(address.split()))] += 1
    stats["hard_group_length_hist"][text_length_bucket(len(address))] += 1
    digits = re.findall(r"\d+", address)
    stats["hard_group_digit_hist"]["0" if not digits else ("1" if len(digits) == 1 else "2+")] += 1
    if "" in name_counts:
        stats["hard_groups_with_empty_name"] += 1

    items = list(name_counts.items())
    for i, (left, lc) in enumerate(items):
        lt = set(left.split())
        lcompact = left.replace(" ", "")
        for right, rc in items[i + 1:]:
            weight = lc * rc
            rt = set(right.split())
            inter = len(lt & rt)
            union = len(lt | rt)
            jaccard = inter / union if union else 0.0
            stats["hard_pair_token_jaccard_bins"][jaccard_bucket(jaccard)] += weight
            stats["hard_pair_mass_by_group_size"][size_bucket] += weight
            if inter:
                stats["hard_pairs_shared_any_name_token"] += weight
            else:
                stats["hard_pairs_zero_name_token_overlap"] += weight
            rcompact = right.replace(" ", "")
            if lcompact[:6] and lcompact[:6] == rcompact[:6]:
                stats["hard_pairs_compact_prefix6_equal"] += weight


def _finalize(stats: dict) -> dict:
    records = stats["records"]
    nonempty = records - stats["empty_address_records"]
    hard_pairs = stats["cross_name_pairs"]
    counters = {k: dict(v) for k, v in stats.items() if isinstance(v, Counter)}
    return {
        "records": records,
        "empty_address_records": stats["empty_address_records"],
        "empty_address_rate": stats["empty_address_records"] / records if records else None,
        "unique_nonempty_addresses": stats["unique_nonempty_addresses"],
        "collision_groups": stats["collision_groups"],
        "collision_records": stats["collision_records"],
        "collision_record_rate_all": stats["collision_records"] / records if records else None,
        "collision_record_rate_nonempty": stats["collision_records"] / nonempty if nonempty else None,
        "collision_pairs": stats["collision_pairs"],
        "same_name_only_collision_groups": stats["same_name_only_collision_groups"],
        "hard_negative_like_groups": stats["hard_negative_like_groups"],
        "hard_negative_like_records": stats["hard_negative_like_records"],
        "hard_negative_like_record_rate_all": stats["hard_negative_like_records"] / records if records else None,
        "cross_name_pairs": hard_pairs,
        "same_name_pairs_within_collisions": stats["same_name_pairs_within_collisions"],
        "cross_name_share_of_collision_pairs": (
            stats["cross_name_pairs"] / stats["collision_pairs"]
            if stats["collision_pairs"] else None
        ),
        "hard_groups_with_empty_name": stats["hard_groups_with_empty_name"],
        "collision_group_size_quantiles": nearest_rank_quantiles(stats["collision_group_sizes"]),
        "hard_group_size_quantiles": nearest_rank_quantiles(stats["hard_group_sizes"]),
        "hard_distinct_name_count_quantiles": nearest_rank_quantiles(stats["hard_distinct_name_counts"]),
        **counters,
        "hard_pairs_shared_any_name_token_rate": (
            stats["hard_pairs_shared_any_name_token"] / hard_pairs if hard_pairs else None
        ),
        "hard_pairs_zero_name_token_overlap_rate": (
            stats["hard_pairs_zero_name_token_overlap"] / hard_pairs if hard_pairs else None
        ),
        "hard_pairs_compact_prefix6_equal_rate": (
            stats["hard_pairs_compact_prefix6_equal"] / hard_pairs if hard_pairs else None
        ),
        "hard_pair_token_jaccard_bin_rates": {
            key: stats["hard_pair_token_jaccard_bins"].get(key, 0) / hard_pairs
            if hard_pairs else None
            for key in ["0", "(0,.25]", "(.25,.5]", "(.5,.75]", "(.75,1)", "1"]
        },
        "hard_pair_mass_by_group_size_rates": {
            key: stats["hard_pair_mass_by_group_size"].get(key, 0) / hard_pairs
            if hard_pairs else None
            for key in ["2", "3-5", "6-10", "11-50", "51+"]
        },
    }


def _write_sorted_chunk(rows: list[tuple[str, str, str]], path: Path) -> None:
    rows.sort()
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, delimiter="\t", lineterminator="\n").writerows(rows)


def _iter_chunk(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.reader(handle, delimiter="\t")


def audit_source1(input_tsv: Path, work_dir: Path, chunk_rows: int = 350_000) -> dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    chunk_paths: list[Path] = []
    chunk: list[tuple[str, str, str]] = []
    raw_counts = Counter()

    with input_tsv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"business_name", "business_address", "country"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                f"missing required columns: {sorted(required - set(reader.fieldnames or []))}"
            )
        for row in reader:
            name = row.get("business_name") or ""
            address = row.get("business_address") or ""
            country = row.get("country") or ""
            raw_counts["records"] += 1
            if not name.isascii():
                raw_counts["nonascii_name_rows"] += 1
            if not address.isascii():
                raw_counts["nonascii_address_rows"] += 1

            # Entity IDs are deliberately omitted before any grouping/similarity.
            chunk.append(
                (country, normalize_repo_like(address), normalize_repo_like(name))
            )
            if len(chunk) >= chunk_rows:
                path = work_dir / f"chunk_{len(chunk_paths):04d}.tsv"
                _write_sorted_chunk(chunk, path)
                chunk_paths.append(path)
                chunk = []

    if chunk:
        path = work_dir / f"chunk_{len(chunk_paths):04d}.tsv"
        _write_sorted_chunk(chunk, path)
        chunk_paths.append(path)

    merged = heapq.merge(
        *[_iter_chunk(path) for path in chunk_paths],
        key=lambda row: (row[0], row[1], row[2]),
    )
    stats = defaultdict(_new_stats)
    for (country, address), group in itertools.groupby(
        merged, key=lambda row: (row[0], row[1])
    ):
        names = [row[2] for row in group]
        _update_group(stats[country], address, names)
        _update_group(stats["ALL"], address, names)

    result = {country: _finalize(value) for country, value in sorted(stats.items())}
    result["protocol"] = {
        "input_records": raw_counts["records"],
        "nonascii_name_rows": raw_counts["nonascii_name_rows"],
        "nonascii_address_rows": raw_counts["nonascii_address_rows"],
        "chunk_rows": chunk_rows,
        "entity_id_used_as_evidence": False,
        "normalization": (
            "lowercase + NFD accent stripping + Unicode letters/digits + collapsed separators"
        ),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="train_source1.tsv")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--chunk-rows", type=int, default=350_000)
    args = parser.parse_args()
    if args.chunk_rows < 1:
        raise ValueError("--chunk-rows must be >= 1")

    if args.work_dir is None:
        with tempfile.TemporaryDirectory(prefix="f004-address-audit-") as tmp:
            result = audit_source1(args.input, Path(tmp), args.chunk_rows)
    else:
        result = audit_source1(args.input, args.work_dir, args.chunk_rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
