"""Dependency-light reference semantics for I025 INT002 v2 feature audit.

This module intentionally does not import the production DuckDB path. It codifies
independent reference behavior for the six v2 features so source audits can test
tie/frequency invariants even in runtimes without DuckDB.
"""
from __future__ import annotations

from collections import Counter
from math import log


def frequency_tables(records):
    """Return country-local left(source1)/right(source>1) name/address counts."""
    out = {}
    for side, predicate in (("left", lambda s: s == 1), ("right", lambda s: s > 1)):
        for field in ("n", "a"):
            counts = Counter(
                (r["country"], r[field])
                for r in records
                if predicate(r["source"]) and r[field] != ""
            )
            out[(side, field)] = counts
    return out


def dense_desc_rank(scores):
    """Score-only dense rank, descending. Equal scores always share rank."""
    levels = {s: i + 1 for i, s in enumerate(sorted(set(scores), reverse=True))}
    return [levels[s] for s in scores]


def extra_rows(anchor, targets, scores, freq):
    """Reference the six model-facing v2 extras for one anchor candidate group."""
    ranks = dense_desc_rank(scores)
    top = max(scores)
    den = max(1.0, top)
    rows = []
    for target, score, rank in zip(targets, scores, ranks):
        rows.append((
            log(1 + freq[("left", "n")].get((anchor["country"], anchor["n"]), 0)),
            log(1 + freq[("left", "a")].get((anchor["country"], anchor["a"]), 0)),
            log(1 + freq[("right", "n")].get((target["country"], target["n"]), 0)),
            log(1 + freq[("right", "a")].get((target["country"], target["a"]), 0)),
            log(1 + rank),
            score / den,
        ))
    return rows


def minimum_blocker_hit_score(max_posting_frequency=1000):
    """Lower bound from one zero-bonus eligible blocker hit."""
    return log(10000001.0 / max_posting_frequency)
