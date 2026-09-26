"""Compatibility helpers for comparing older matchers on v3 fused candidates."""
from __future__ import annotations

import numpy as np


def v2_prefix_from_v3(x, groups, v2_feature_names):
    """Restore v2 relative-retrieval semantics in a v3 feature prefix.

    V3 fused RRF retrieval scores are below one and v3 normalizes by the
    per-anchor maximum. V2 divides by max(1, top_retrieval). A frozen v2 model
    evaluated on a v3 candidate pool must reconstruct this feature rather than
    consume the v3-normalized value.
    """
    x = np.asarray(x)
    groups = np.asarray(groups)
    width = len(v2_feature_names)
    if x.ndim != 2 or x.shape[1] < width:
        raise ValueError("feature matrix is narrower than the v2 schema")
    if groups.ndim != 1 or len(groups) != len(x):
        raise ValueError("groups must be one-dimensional and aligned with rows")
    try:
        retrieval_i = v2_feature_names.index("retrieval")
        relative_i = v2_feature_names.index("relative_retrieval_score")
    except ValueError as exc:
        raise ValueError("v2 schema is missing retrieval features") from exc

    out = x[:, :width].copy()
    for group in np.unique(groups):
        mask = groups == group
        retrieval = out[mask, retrieval_i]
        top = float(np.max(retrieval))
        out[mask, relative_i] = retrieval / max(1.0, top)
    return out
