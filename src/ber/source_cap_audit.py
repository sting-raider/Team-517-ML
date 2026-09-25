"""Reference audit for target-source allocation under a joint candidate cap.

This module does not alter production retrieval. It mirrors the final blocker
ranking semantics after retrieval scores are computed so source-allocation
policies can be reasoned about and tested without challenge rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Candidate:
    entity_id: str
    source: int
    retrieval: float


def _global_key(row: Candidate) -> tuple[float, str]:
    return (-row.retrieval, row.entity_id)


def select_joint(rows: Iterable[Candidate], cap: int) -> list[Candidate]:
    """Mirror blocker v2's final global top-k ranking across S2 and S3."""
    if cap < 1:
        raise ValueError("cap must be >= 1")
    return sorted(rows, key=_global_key)[:cap]


def select_with_source_floor(
    rows: Iterable[Candidate],
    cap: int,
    source_floor: int = 1,
) -> list[Candidate]:
    """Reference policy reserving a small floor for each target source.

    This is analysis-only. It is intentionally not wired into production
    blocking without a full-data benchmark.
    """
    if cap < 1:
        raise ValueError("cap must be >= 1")
    if source_floor < 0:
        raise ValueError("source_floor must be >= 0")
    if 2 * source_floor > cap:
        raise ValueError("2*source_floor must be <= cap for target sources 2 and 3")

    rows = list(rows)
    source_rank: dict[Candidate, int] = {}
    for source in (2, 3):
        ranked = sorted(
            (row for row in rows if row.source == source),
            key=_global_key,
        )
        source_rank.update({row: index + 1 for index, row in enumerate(ranked)})

    def key(row: Candidate) -> tuple[int, float, str]:
        reserved = source_rank.get(row, 10**9) <= source_floor
        return (0 if reserved else 1, -row.retrieval, row.entity_id)

    return sorted(rows, key=key)[:cap]


def audit(
    rows: Iterable[Candidate],
    cap: int,
    source_floor: int = 1,
) -> dict[str, object]:
    rows = list(rows)
    joint = select_joint(rows, cap)
    floored = select_with_source_floor(rows, cap, source_floor)

    joint_ids = {row.entity_id for row in joint}
    floored_ids = {row.entity_id for row in floored}
    return {
        "joint_ids": [row.entity_id for row in joint],
        "joint_sources": [row.source for row in joint],
        "floored_ids": [row.entity_id for row in floored],
        "floored_sources": [row.source for row in floored],
        "displaced": sorted(joint_ids - floored_ids),
        "added": sorted(floored_ids - joint_ids),
        "changed_count": len(joint_ids.symmetric_difference(floored_ids)) // 2,
    }


def demo() -> dict[str, dict[str, object]]:
    scenarios = {
        "strict_source2_dominance": (
            [
                Candidate("s2_a", 2, 100.0),
                Candidate("s2_b", 2, 99.0),
                Candidate("s3_a", 3, 90.0),
            ],
            2,
        ),
        "equal_score_tie_starvation": (
            [
                Candidate("a_s2", 2, 100.0),
                Candidate("b_s2", 2, 100.0),
                Candidate("z_s3", 3, 100.0),
            ],
            2,
        ),
        "already_balanced": (
            [
                Candidate("s2_a", 2, 100.0),
                Candidate("s3_a", 3, 99.0),
                Candidate("s2_b", 2, 80.0),
            ],
            2,
        ),
        "single_source_available": (
            [
                Candidate("s2_a", 2, 100.0),
                Candidate("s2_b", 2, 90.0),
            ],
            2,
        ),
    }
    return {
        name: audit(rows, cap=cap, source_floor=1)
        for name, (rows, cap) in scenarios.items()
    }


if __name__ == "__main__":
    import json

    print(json.dumps(demo(), indent=2))
