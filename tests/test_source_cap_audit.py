import random

import pytest

from ber.source_cap_audit import (
    Candidate,
    audit,
    select_joint,
    select_with_source_floor,
)


def test_joint_cap_can_starve_source3():
    rows = [
        Candidate("s2_a", 2, 100.0),
        Candidate("s2_b", 2, 99.0),
        Candidate("s3_a", 3, 90.0),
    ]
    assert [row.source for row in select_joint(rows, 2)] == [2, 2]
    assert [row.source for row in select_with_source_floor(rows, 2, 1)] == [2, 3]


def test_entity_id_tie_break_can_starve_source3():
    rows = [
        Candidate("a_s2", 2, 100.0),
        Candidate("b_s2", 2, 100.0),
        Candidate("z_s3", 3, 100.0),
    ]
    assert [row.entity_id for row in select_joint(rows, 2)] == ["a_s2", "b_s2"]
    assert [row.entity_id for row in select_with_source_floor(rows, 2, 1)] == [
        "a_s2",
        "z_s3",
    ]


def test_floor_is_noop_when_global_topk_already_covers_both_sources():
    rows = [
        Candidate("s2_a", 2, 100.0),
        Candidate("s3_a", 3, 99.0),
        Candidate("s2_b", 2, 80.0),
    ]
    assert select_with_source_floor(rows, 2, 1) == select_joint(rows, 2)


def test_floor_does_not_waste_capacity_if_only_one_source_is_available():
    rows = [
        Candidate("s2_a", 2, 100.0),
        Candidate("s2_b", 2, 90.0),
    ]
    assert select_with_source_floor(rows, 2, 1) == select_joint(rows, 2)


def test_source_floor_zero_exactly_matches_joint_selector():
    rng = random.Random(517)
    for _ in range(200):
        rows = [
            Candidate(
                f"id_{i:03d}",
                2 if rng.random() < 0.5 else 3,
                float(rng.randrange(5)),
            )
            for i in range(rng.randrange(1, 60))
        ]
        cap = rng.randrange(1, min(20, len(rows)) + 1)
        assert select_with_source_floor(rows, cap, 0) == select_joint(rows, cap)


def test_floor_one_changes_at_most_one_candidate_when_both_sources_exist():
    rng = random.Random(517019)
    for _ in range(500):
        rows = [
            Candidate(
                f"id_{i:03d}",
                2 if rng.random() < 0.5 else 3,
                rng.random(),
            )
            for i in range(rng.randrange(2, 80))
        ]
        if {row.source for row in rows} != {2, 3}:
            continue
        cap = rng.randrange(2, min(30, len(rows)) + 1)
        result = audit(rows, cap, source_floor=1)
        assert result["changed_count"] <= 1
        assert {2, 3}.issubset(set(result["floored_sources"]))


def test_invalid_floor_is_rejected():
    rows = [Candidate("s2", 2, 1.0), Candidate("s3", 3, 1.0)]
    with pytest.raises(ValueError):
        select_with_source_floor(rows, cap=1, source_floor=1)
