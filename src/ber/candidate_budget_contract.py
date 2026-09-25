"""Shared raw-retrieval ranking contract for candidate-budget evaluation."""
import numpy as np


def raw_retrieval_rank(groups, targets, retrieval):
    """Return 1-based per-anchor rank matching blocker SQL ordering.

    Production blocker ordering is retrieval DESC, target entity_id ASC within
    each anchor. Inputs are parallel arrays and may be empty.
    """
    groups = np.asarray(groups)
    targets = np.asarray(targets)
    retrieval = np.asarray(retrieval)
    if not (len(groups) == len(targets) == len(retrieval)):
        raise ValueError("groups, targets, and retrieval must have equal lengths")
    if len(groups) == 0:
        return np.empty(0, dtype=np.int32)
    order = np.lexsort((targets, -retrieval, groups))
    starts = np.r_[0, np.flatnonzero(np.diff(groups[order])) + 1]
    rank = np.empty(len(order), dtype=np.int32)
    rank[order] = (
        np.arange(len(order))
        - np.repeat(starts, np.diff(np.r_[starts, len(order)]))
        + 1
    )
    return rank
