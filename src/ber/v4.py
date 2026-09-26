"""INT004: address token alignment on the unchanged v3 candidate pool."""
import numpy as np

from .soft_alignment import ADDRESS_SOFT_ALIGNMENT_FEATURE_NAMES, address_soft_alignment_features
from .v2 import compute_rows as compute_v3_rows, materialize as materialize_base
from .v3 import V3_NAMES, pair_query
from .retrieval_v3 import build_char_index, fused_candidates

V4_NAMES = V3_NAMES + ADDRESS_SOFT_ALIGNMENT_FEATURE_NAMES


def compute_rows(rows):
    ids, base = compute_v3_rows(rows)
    aligned = np.asarray(
        [address_soft_alignment_features(row[3], row[5]) for row in rows],
        dtype=np.float32,
    )
    values = np.concatenate((base, aligned), axis=1)
    if values.shape[1] != len(V4_NAMES):
        raise ValueError('V4 feature query/schema mismatch')
    return ids, values


def materialize(db, out, partition=0, partitions=8, confirmation=False):
    return materialize_base(
        db, out, partition, partitions, confirmation=confirmation,
        candidate_fn=fused_candidates, query_fn=pair_query,
        feature_names=V4_NAMES, index_fn=build_char_index,
        confirmation_start=200000, compute_fn=compute_rows,
    )
