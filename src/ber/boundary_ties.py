"""Pure helpers for auditing exact-score hard-cap tie dependence.

Rows are triples ``(score, tie_id, item_id)``. ``tie_id`` is the secondary
identifier used by a candidate implementation, while ``item_id`` is the
candidate identity used for truth/evaluation. The helpers never use truth to
rank or select candidates.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def rank_rows(rows: Iterable[tuple[float, object, object]], *, tie_desc: bool) -> list[tuple[float, object, object]]:
    """Sort by descending score and then by the requested identifier direction."""
    values = [(float(score), tie_id, item_id) for score, tie_id, item_id in rows]
    for score, _, _ in values:
        if not math.isfinite(score):
            raise ValueError("Candidate scores must be finite")
    values.sort(key=lambda row: row[1], reverse=tie_desc)
    values.sort(key=lambda row: row[0], reverse=True)
    return values


def boundary_tie(
    ranked: Sequence[tuple[float, object, object]],
    cutoff: int,
    *,
    truth_items: set[object] | None = None,
) -> dict | None:
    """Describe an exact-score tie that straddles ``cutoff``.

    ``ranked`` must already be in non-increasing score order. Returned truth
    bounds are diagnostic only: they describe how many true items could be
    selected from the tied group under alternate *label-blind* tie orders.
    """
    if cutoff <= 0:
        raise ValueError("cutoff must be positive")
    if cutoff >= len(ranked):
        return None
    scores = [float(row[0]) for row in ranked]
    if any(not math.isfinite(score) for score in scores):
        raise ValueError("Candidate scores must be finite")
    if any(scores[i] < scores[i + 1] for i in range(len(scores) - 1)):
        raise ValueError("ranked rows must have non-increasing scores")
    boundary_score = scores[cutoff - 1]
    if scores[cutoff] != boundary_score:
        return None
    start = cutoff - 1
    while start > 0 and scores[start - 1] == boundary_score:
        start -= 1
    end = cutoff
    while end + 1 < len(scores) and scores[end + 1] == boundary_score:
        end += 1
    end += 1
    group = ranked[start:end]
    selected_from_tie = cutoff - start
    excluded_from_tie = end - cutoff
    result = {
        "score": boundary_score,
        "tie_start": start,
        "tie_end": end,
        "tie_size": len(group),
        "selected_from_tie": selected_from_tie,
        "excluded_from_tie": excluded_from_tie,
        "max_membership_symmetric_difference": 2 * min(selected_from_tie, excluded_from_tie),
    }
    if truth_items is not None:
        truth_total = sum(row[2] in truth_items for row in group)
        actual_truth = sum(row[2] in truth_items for row in group[:selected_from_tie])
        truth_min = max(0, selected_from_tie - (len(group) - truth_total))
        truth_max = min(selected_from_tie, truth_total)
        result.update(
            truth_in_tie=truth_total,
            actual_selected_truth=actual_truth,
            min_selected_truth=truth_min,
            max_selected_truth=truth_max,
            true_link_span=truth_max - truth_min,
        )
    return result


def select_prefix_by_score_id(
    rows: Iterable[tuple[float, object, object]], cutoff: int, *, tie_desc: bool
) -> list[tuple[float, object, object]]:
    """Select a hard prefix under an explicit score+identifier order."""
    return rank_rows(rows, tie_desc=tie_desc)[:cutoff]


def select_final_pool(
    dense: Sequence[tuple[float, object, object]],
    base: Sequence[tuple[float, object, object]],
    *,
    cap: int = 32,
    base_pre_cap: int = 32,
) -> list[tuple[float, object, object]]:
    """Mirror INT006 priority: dense first, then base rows, deduplicated by item."""
    if cap <= 0 or base_pre_cap <= 0:
        raise ValueError("caps must be positive")
    picked: list[tuple[float, object, object]] = []
    seen: set[object] = set()
    for row in dense:
        if row[2] not in seen:
            picked.append(row)
            seen.add(row[2])
        if len(picked) >= cap:
            return picked
    for row in base[:base_pre_cap]:
        if row[2] not in seen:
            picked.append(row)
            seen.add(row[2])
        if len(picked) >= cap:
            break
    return picked


def filtered_base_boundary(
    base_ranked: Sequence[tuple[float, object, object]],
    dense_item_ids: set[object],
    *,
    final_cap: int = 32,
    dense_slots: int = 16,
) -> dict | None:
    """Audit the base-score boundary after removing dense duplicates."""
    needed = final_cap - dense_slots
    if needed <= 0:
        return None
    eligible = [row for row in base_ranked if row[2] not in dense_item_ids]
    return boundary_tie(eligible, needed)


def quantile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    if not 0 <= q <= 1:
        raise ValueError("q must be in [0,1]")
    ordered = sorted(float(v) for v in values)
    pos = q * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def summarize_ties(details: Sequence[dict | None], *, anchors: int | None = None) -> dict:
    ties = [d for d in details if d is not None]
    denom = len(details) if anchors is None else anchors
    if denom < len(ties):
        raise ValueError("anchor denominator smaller than tie count")
    widths = [d["tie_size"] for d in ties]
    spans = [d.get("true_link_span", 0) for d in ties]
    return {
        "anchors": denom,
        "tie_anchors": len(ties),
        "tie_rate": len(ties) / denom if denom else 0.0,
        "tie_size_p50": quantile(widths, 0.50),
        "tie_size_p90": quantile(widths, 0.90),
        "tie_size_p99": quantile(widths, 0.99),
        "tie_size_max": max(widths) if widths else 0,
        "max_membership_symmetric_difference_total": sum(
            d["max_membership_symmetric_difference"] for d in ties
        ),
        "truth_sensitive_tie_anchors": sum(span > 0 for span in spans),
        "true_link_span_total": sum(spans),
    }
