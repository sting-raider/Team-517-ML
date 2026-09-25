"""Exact data-dependent threshold selection for per-anchor macro F0.5.

The production pipeline currently uses experiment.choose_threshold, which searches
an explicit coarse grid. This module is opt-in analysis code: it enumerates every
prediction set reachable by a probability threshold without changing candidates,
model probabilities, or the official row metric.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np


def _row_score_from_counts(truth_size: int, tp: int, predicted: int) -> float:
    if truth_size == 0:
        return float(predicted == 0)
    return 1.25 * tp / (0.25 * truth_size + predicted)


def choose_threshold_exact(meta, groups, target, prob, indices: Iterable[int]):
    """Return the exact best threshold over observed probability breakpoints.

    Semantics intentionally match experiment.choose_threshold:
    - predictions use prob >= threshold;
    - truth members missing from the candidate set remain in the denominator;
    - empty-truth/empty-prediction rows score one;
    - macro averaging is over the supplied anchor indices;
    - exact score ties prefer the higher threshold.

    The returned diagnostic dict is aggregate-only and deliberately does not
    contain row IDs or predictions.
    """
    ids = np.asarray(list(indices), dtype=np.int64)
    if ids.size == 0:
        raise ValueError("indices must be non-empty")
    if np.unique(ids).size != ids.size:
        raise ValueError("indices must be unique")
    if ids.min() < 0 or ids.max() >= len(meta):
        raise ValueError("indices contain an out-of-range anchor")

    groups = np.asarray(groups)
    target = np.asarray(target)
    prob = np.asarray(prob, dtype=float)
    if not (len(groups) == len(target) == len(prob)):
        raise ValueError("groups, target, and prob must have equal lengths")

    mask = np.isin(groups, ids)
    gs = np.asarray(groups[mask], dtype=np.int64)
    ts = target[mask]
    ps = prob[mask]
    if gs.size and (gs.min() < 0 or gs.max() >= len(meta)):
        raise ValueError("groups contain an out-of-range anchor")
    if np.any(~np.isfinite(ps)) or np.any((ps < 0.0) | (ps > 1.0)):
        raise ValueError("probabilities must be finite and within [0, 1]")

    truth_sizes = np.asarray([len(m["truth"]) for m in meta], dtype=np.int64)
    labels = np.fromiter(
        (t in meta[int(g)]["truth"] for g, t in zip(gs, ts)),
        dtype=bool,
        count=len(gs),
    )

    predicted = np.zeros(len(meta), dtype=np.int64)
    tp = np.zeros(len(meta), dtype=np.int64)
    row_scores = np.zeros(len(meta), dtype=float)
    row_scores[truth_sizes == 0] = 1.0
    total = float(row_scores[ids].sum())

    best_threshold = None
    best_score = -math.inf
    evaluated_states = 0

    def consider(threshold: float) -> None:
        nonlocal best_threshold, best_score, evaluated_states
        score = total / ids.size
        evaluated_states += 1
        if (
            score > best_score
            or (score == best_score and (best_threshold is None or threshold > best_threshold))
        ):
            best_score = float(score)
            best_threshold = float(threshold)

    if ps.size == 0:
        consider(1.0)
    else:
        order = np.argsort(-ps, kind="stable")
        # threshold=1.0 yields the empty prediction set only when max(prob)<1.
        if float(ps[order[0]]) < 1.0:
            consider(1.0)

        pos = 0
        while pos < len(order):
            value = float(ps[order[pos]])
            end = pos + 1
            while end < len(order) and float(ps[order[end]]) == value:
                end += 1

            # Equal-probability rows enter together because the rule is >=.
            affected = {}
            for oi in order[pos:end]:
                g = int(gs[oi])
                if g not in affected:
                    affected[g] = row_scores[g]
                predicted[g] += 1
                if labels[oi]:
                    tp[g] += 1

            for g, old_score in affected.items():
                new_score = _row_score_from_counts(
                    int(truth_sizes[g]), int(tp[g]), int(predicted[g])
                )
                row_scores[g] = new_score
                total += new_score - old_score

            consider(value)
            pos = end

    assert best_threshold is not None
    return best_threshold, {
        "macro_f0_5": best_score,
        "evaluated_states": evaluated_states,
        "candidate_rows": int(ps.size),
        "anchors": int(ids.size),
    }
