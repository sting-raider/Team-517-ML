"""Analysis helpers for the blocker-v2 posting-frequency eligibility cliff.

This module mirrors the scalar scoring semantics in src/ber/blocking.py.  It is
not wired into production retrieval; R023 is a diagnostic experiment only.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

DEFAULT_MAX_FREQ = 1000
IDF_NUMERATOR = 10_000_001.0
BONUS_BY_KIND = {
    "n:": 50.0,
    "a:": 40.0,
    "w:": 0.0,
    "h:": 8.0,
    "z:": 8.0,
    "u:": 8.0,
    "v:": 8.0,
    "d:": 8.0,
}


def _validate(kind: str, freq: int) -> None:
    if kind not in BONUS_BY_KIND:
        raise ValueError(f"unknown blocker key kind: {kind!r}")
    if freq < 1:
        raise ValueError("freq must be >= 1")


def smooth_contribution(kind: str, freq: int) -> float:
    """Contribution the current formula would assign absent the hard cutoff."""
    _validate(kind, freq)
    return BONUS_BY_KIND[kind] + math.log(IDF_NUMERATOR / freq)


def current_contribution(
    kind: str,
    freq: int,
    *,
    max_freq: int = DEFAULT_MAX_FREQ,
) -> float | None:
    """Mirror blocker-v2: keys above max_freq are ineligible and contribute nothing."""
    _validate(kind, freq)
    if max_freq < 1:
        raise ValueError("max_freq must be >= 1")
    return smooth_contribution(kind, freq) if freq <= max_freq else None


def family_aware_contribution(
    kind: str,
    freq: int,
    *,
    max_freq_by_kind: Mapping[str, int],
    default_max_freq: int = DEFAULT_MAX_FREQ,
) -> float | None:
    """Diagnostic alternative with an eligibility cutoff chosen by key family.

    This deliberately does not prescribe cutoffs and is not used by production
    blocking.  It exists so a later full-data experiment can isolate the effect
    of changing eligibility for exact keys without changing the score formula.
    """
    limit = max_freq_by_kind.get(kind, default_max_freq)
    return current_contribution(kind, freq, max_freq=limit)


@dataclass(frozen=True)
class Cliff:
    kind: str
    boundary: int
    allowed_score: float
    next_smooth_score: float
    smooth_delta: float
    actual_drop: float


def cliff(kind: str, boundary: int = DEFAULT_MAX_FREQ) -> Cliff:
    """Quantify the discontinuity between boundary and boundary+1."""
    if boundary < 1:
        raise ValueError("boundary must be >= 1")
    allowed = current_contribution(kind, boundary, max_freq=boundary)
    assert allowed is not None
    next_smooth = smooth_contribution(kind, boundary + 1)
    return Cliff(
        kind=kind,
        boundary=boundary,
        allowed_score=allowed,
        next_smooth_score=next_smooth,
        smooth_delta=allowed - next_smooth,
        actual_drop=allowed,
    )


def synthetic_rank_score(
    base_score: float,
    *,
    exact_kind: str,
    exact_freq: int,
    max_freq: int = DEFAULT_MAX_FREQ,
) -> float:
    """Score an already-retrieved synthetic candidate plus one exact-key hit.

    base_score represents other eligible blocker evidence.  This lets R023 show
    cap-rank inversions caused solely by exact-key eligibility.
    """
    if exact_kind not in {"n:", "a:"}:
        raise ValueError("exact_kind must be 'n:' or 'a:'")
    extra = current_contribution(exact_kind, exact_freq, max_freq=max_freq)
    return float(base_score) + (0.0 if extra is None else extra)
