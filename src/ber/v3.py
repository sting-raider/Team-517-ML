"""Character-plus-lexical candidate pool with provenance-aware pair evidence."""
from .v2 import V2_NAMES,materialize as materialize_v2
from .retrieval_v3 import build_char_index,fused_candidates

V3_NAMES=V2_NAMES+['log_lexical_retrieval','log_character_retrieval',
    'log_lexical_hits','log_character_hits']


def pair_query(split,anchors,pairs):
    return f'''WITH ranked AS (
        SELECT p.*,dense_rank() OVER(PARTITION BY anchor ORDER BY retrieval DESC) AS ranking,
               max(retrieval) OVER(PARTITION BY anchor) AS top_retrieval
        FROM {pairs} p)
        SELECT p.anchor,r.entity_id,l.n,l.a,r.n,r.a,p.retrieval,p.hits,r.source,
          ln(1+coalesce(lnf.freq,0)),ln(1+coalesce(laf.freq,0)),
          ln(1+coalesce(rnf.freq,0)),ln(1+coalesce(raf.freq,0)),
          ln(1+p.ranking),p.retrieval/greatest(0.000001,p.top_retrieval),
          ln(1+p.base_retrieval),ln(1+p.char_retrieval),
          ln(1+p.base_hits),ln(1+p.char_hits)
        FROM ranked p JOIN {anchors} l ON p.anchor=l.entity_id
        JOIN {split} r ON p.rid=r.rowid
        LEFT JOIN v2_left_n lnf ON l.country=lnf.country AND l.n=lnf.n
        LEFT JOIN v2_left_a laf ON l.country=laf.country AND l.a=laf.a
        LEFT JOIN v2_right_n rnf ON r.country=rnf.country AND r.n=rnf.n
        LEFT JOIN v2_right_a raf ON r.country=raf.country AND r.a=raf.a
        ORDER BY p.anchor,r.entity_id'''


def materialize(db,out,partition=0,partitions=8,confirmation=False,
                confirmation_reason=None,confirmation_freeze=None):
    return materialize_v2(db,out,partition,partitions,confirmation=confirmation,
        candidate_fn=fused_candidates,query_fn=pair_query,
        feature_names=V3_NAMES,index_fn=build_char_index,confirmation_start=45000,
        confirmation_reason=confirmation_reason,confirmation_freeze=confirmation_freeze)


def score_rows(rows):
    """The first 53 fields retain the v2 schema; four expose retrieval channels."""
    from .v2 import compute_rows
    ids,x=compute_rows(rows)
    if x.shape[1]!=len(V3_NAMES):
        raise ValueError('V3 feature query/schema mismatch')
    return ids,x
