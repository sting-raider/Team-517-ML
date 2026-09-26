"""INT003 candidate pool plus opt-in numeric-token commonness evidence."""
from .number_commonness import (
    NUMBER_COMMONNESS_NAMES,
    build_number_commonness,
    profile_joins,
    select_expressions,
)
from .retrieval_v3 import build_char_index, fused_candidates
from .v2 import materialize as materialize_v2
from .v3 import V3_NAMES


V4_NAMES = V3_NAMES + NUMBER_COMMONNESS_NAMES


def build_indexes(c, split):
    build_char_index(c, split)
    build_number_commonness(c, split)


def pair_query(split, anchors, pairs):
    extras = ",\n          ".join(select_expressions())
    number_joins = profile_joins(split)
    return f"""WITH ranked AS (
        SELECT p.*,dense_rank() OVER(PARTITION BY anchor ORDER BY retrieval DESC) AS ranking,
               max(retrieval) OVER(PARTITION BY anchor) AS top_retrieval
        FROM {pairs} p)
        SELECT p.anchor,r.entity_id,l.n,l.a,r.n,r.a,p.retrieval,p.hits,r.source,
          ln(1+coalesce(lnf.freq,0)),ln(1+coalesce(laf.freq,0)),
          ln(1+coalesce(rnf.freq,0)),ln(1+coalesce(raf.freq,0)),
          ln(1+p.ranking),p.retrieval/greatest(0.000001,p.top_retrieval),
          ln(1+p.base_retrieval),ln(1+p.char_retrieval),
          ln(1+p.base_hits),ln(1+p.char_hits),
          {extras}
        FROM ranked p JOIN {anchors} l ON p.anchor=l.entity_id
        JOIN {split} r ON p.rid=r.rowid
        LEFT JOIN v2_left_n lnf ON l.country=lnf.country AND l.n=lnf.n
        LEFT JOIN v2_left_a laf ON l.country=laf.country AND l.a=laf.a
        LEFT JOIN v2_right_n rnf ON r.country=rnf.country AND r.n=rnf.n
        LEFT JOIN v2_right_a raf ON r.country=raf.country AND r.a=raf.a
        {number_joins}
        ORDER BY p.anchor,r.entity_id"""


def materialize(db, out, partition=0, partitions=8, confirmation=False):
    return materialize_v2(
        db,
        out,
        partition,
        partitions,
        confirmation=confirmation,
        candidate_fn=fused_candidates,
        query_fn=pair_query,
        feature_names=V4_NAMES,
        index_fn=build_indexes,
        confirmation_start=45000,
    )


def score_rows(rows):
    """V3 is an exact prefix; eight numeric-commonness fields are appended."""
    from .v2 import compute_rows

    ids, x = compute_rows(rows)
    if x.shape[1] != len(V4_NAMES):
        raise ValueError("V4 feature query/schema mismatch")
    return ids, x
