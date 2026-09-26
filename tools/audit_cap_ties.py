"""R026: deterministic audit of ID-sensitive retrieval hard-cap tie semantics.

This is an analysis helper, not production retrieval logic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Candidate:
    physical: str
    entity_id: str
    score: float
    hits: int = 1


def legacy_exact_cap(rows: Iterable[Candidate], cap: int) -> list[Candidate]:
    """Mirror current `ORDER BY score DESC, entity_id` exact-cap semantics."""
    if cap < 1:
        raise ValueError("cap must be positive")
    return sorted(rows, key=lambda r: (-r.score, r.entity_id))[:cap]


def boundary_tie_cap(rows: Iterable[Candidate], cap: int, use_hits: bool = False) -> list[Candidate]:
    """ID-invariant reference: include the complete evidence tie at the cap boundary.

    With use_hits=True, (score, hits) is treated as the evidence tuple. This can
    resolve some score ties, but if the full evidence tuple still ties at the
    boundary all tied candidates are retained.
    """
    rows = list(rows)
    if cap < 1:
        raise ValueError("cap must be positive")
    if len(rows) <= cap:
        return sorted(rows, key=lambda r: (-r.score, -r.hits if use_hits else 0))
    evidence = (lambda r: (r.score, r.hits)) if use_hits else (lambda r: (r.score,))
    ordered = sorted((evidence(r) for r in rows), reverse=True)
    cutoff = ordered[cap - 1]
    return [r for r in rows if evidence(r) >= cutoff]


def _boundary_case() -> dict:
    fixed = [Candidate(f"fixed-{i}", f"F{i:03d}", 1000.0 - i, 3) for i in range(158)]
    physical = [f"tie-{i}" for i in range(5)]
    ids_a = ["A", "B", "C", "D", "E"]
    ids_b = list(reversed(ids_a))
    a = fixed + [Candidate(p, eid, 100.0, 2) for p, eid in zip(physical, ids_a)]
    b = fixed + [Candidate(p, eid, 100.0, 2) for p, eid in zip(physical, ids_b)]
    legacy_a = {r.physical for r in legacy_exact_cap(a, 160)}
    legacy_b = {r.physical for r in legacy_exact_cap(b, 160)}
    safe_a = {r.physical for r in boundary_tie_cap(a, 160)}
    safe_b = {r.physical for r in boundary_tie_cap(b, 160)}
    return {
        "cap": 160,
        "rows": len(a),
        "legacy_count": len(legacy_a),
        "legacy_membership_symmetric_difference_after_id_permutation": len(legacy_a ^ legacy_b),
        "boundary_tie_count": len(safe_a),
        "boundary_tie_overflow": len(safe_a) - 160,
        "boundary_tie_invariant": safe_a == safe_b,
    }


def _no_boundary_tie_case() -> dict:
    rows = [Candidate(f"p{i}", f"ID{i:03d}", float(500 - i), 1) for i in range(200)]
    reversed_ids = list(reversed([r.entity_id for r in rows]))
    permuted = [Candidate(r.physical, eid, r.score, r.hits) for r, eid in zip(rows, reversed_ids)]
    legacy_a = {r.physical for r in legacy_exact_cap(rows, 160)}
    legacy_b = {r.physical for r in legacy_exact_cap(permuted, 160)}
    safe = {r.physical for r in boundary_tie_cap(rows, 160)}
    return {
        "cap": 160,
        "legacy_invariant": legacy_a == legacy_b,
        "legacy_matches_boundary_tie_policy": legacy_a == safe,
        "selected": len(safe),
    }


def _secondary_evidence_case() -> dict:
    fixed = [Candidate(f"fixed-{i}", f"F{i:03d}", 1000.0 - i, 3) for i in range(158)]
    tied = [
        Candidate("tie-a", "A", 100.0, 3),
        Candidate("tie-b", "B", 100.0, 3),
        Candidate("tie-c", "C", 100.0, 2),
        Candidate("tie-d", "D", 100.0, 2),
        Candidate("tie-e", "E", 100.0, 2),
    ]
    score_only = boundary_tie_cap(fixed + tied, 160)
    score_hits = boundary_tie_cap(fixed + tied, 160, use_hits=True)
    return {
        "score_only_count": len(score_only),
        "score_hits_count": len(score_hits),
        "score_hits_exact_cap": len(score_hits) == 160,
        "note": "legitimate secondary evidence resolves this constructed score tie, but not all possible full-evidence ties",
    }


def audit() -> dict:
    return {
        "boundary_crossing_tie": _boundary_case(),
        "no_boundary_tie": _no_boundary_tie_case(),
        "secondary_evidence": _secondary_evidence_case(),
    }


def main() -> None:
    print(json.dumps(audit(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
