"""INT003-compatible matcher features with source-local token IDF evidence."""
from .idf import IDF_FEATURE_NAMES, ensure_token_idf_tables, table_names
from .retrieval_v3 import build_char_index, fused_candidates
from .v2 import materialize as materialize_v2
from .v3 import V3_NAMES

V5_NAMES = V3_NAMES + IDF_FEATURE_NAMES


def pair_query(split, anchors, pairs):
    profile, token_table, _ = table_names(split)
    return f'''WITH ranked AS (
        SELECT p.*,dense_rank() OVER(PARTITION BY anchor ORDER BY retrieval DESC) AS ranking,
               max(retrieval) OVER(PARTITION BY anchor) AS top_retrieval
        FROM {pairs} p),
    joined AS (
        SELECT p.anchor,p.rid,r.entity_id,l.country,r.country AS right_country,l.n AS ln,l.a AS la,r.n AS rn,r.a AS ra,
          p.retrieval,p.hits,r.source AS right_source,
          ln(1+coalesce(lnf.freq,0)) AS log_lnf,ln(1+coalesce(laf.freq,0)) AS log_laf,
          ln(1+coalesce(rnf.freq,0)) AS log_rnf,ln(1+coalesce(raf.freq,0)) AS log_raf,
          ln(1+p.ranking) AS log_rank,p.retrieval/greatest(0.000001,p.top_retrieval) AS relative_retrieval,
          ln(1+p.base_retrieval) AS log_lexical_retrieval,
          ln(1+p.char_retrieval) AS log_character_retrieval,
          ln(1+p.base_hits) AS log_lexical_hits,ln(1+p.char_hits) AS log_character_hits
        FROM ranked p JOIN {anchors} l ON p.anchor=l.entity_id
        JOIN {split} r ON p.rid=r.rowid
        LEFT JOIN v2_left_n lnf ON l.country=lnf.country AND l.n=lnf.n
        LEFT JOIN v2_left_a laf ON l.country=laf.country AND l.a=laf.a
        LEFT JOIN v2_right_n rnf ON r.country=rnf.country AND r.n=rnf.n
        LEFT JOIN v2_right_a raf ON r.country=raf.country AND r.a=raf.a),
    membership AS (
        SELECT anchor,rid,'name' AS field,token,1::INTEGER AS in_left,0::INTEGER AS in_right
        FROM joined,unnest(list_distinct(string_split(ln,' '))) AS u(token) WHERE token<>''
        UNION ALL
        SELECT anchor,rid,'name' AS field,token,0::INTEGER AS in_left,1::INTEGER AS in_right
        FROM joined,unnest(list_distinct(string_split(rn,' '))) AS u(token) WHERE token<>''
        UNION ALL
        SELECT anchor,rid,'address' AS field,token,1::INTEGER AS in_left,0::INTEGER AS in_right
        FROM joined,unnest(list_distinct(string_split(la,' '))) AS u(token) WHERE token<>''
        UNION ALL
        SELECT anchor,rid,'address' AS field,token,0::INTEGER AS in_left,1::INTEGER AS in_right
        FROM joined,unnest(list_distinct(string_split(ra,' '))) AS u(token) WHERE token<>''),
    tokens AS (
        SELECT anchor,rid,field,token,max(in_left) AS in_left,max(in_right) AS in_right
        FROM membership GROUP BY anchor,rid,field,token),
    weighted AS (
        SELECT t.anchor,t.rid,t.field,t.in_left,t.in_right,
          0.5*(coalesce(ldf.idf,ln(lp.nrows+1.0)+1.0)+
               coalesce(rdf.idf,ln(rp.nrows+1.0)+1.0)) AS w
        FROM tokens t JOIN joined j USING(anchor,rid)
        JOIN {profile} lp ON lp.source=1 AND lp.country=j.country
        JOIN {profile} rp ON rp.source=j.right_source AND rp.country=j.right_country
        LEFT JOIN {token_table} ldf ON ldf.source=1 AND ldf.country=j.country
          AND ldf.field=t.field AND ldf.token=t.token
        LEFT JOIN {token_table} rdf ON rdf.source=j.right_source AND rdf.country=j.right_country
          AND rdf.field=t.field AND rdf.token=t.token),
    aggregate AS (
        SELECT anchor,rid,field,
          sum(w) AS union_mass,
          coalesce(sum(w) FILTER (WHERE in_left=1 AND in_right=1),0.0) AS shared_mass,
          coalesce(sum(w) FILTER (WHERE in_left=1),0.0) AS left_mass,
          coalesce(sum(w) FILTER (WHERE in_right=1),0.0) AS right_mass
        FROM weighted GROUP BY anchor,rid,field),
    pivoted AS (
        SELECT anchor,rid,
          max(union_mass) FILTER (WHERE field='name') AS name_union,
          max(shared_mass) FILTER (WHERE field='name') AS name_shared,
          max(left_mass) FILTER (WHERE field='name') AS name_left,
          max(right_mass) FILTER (WHERE field='name') AS name_right,
          max(union_mass) FILTER (WHERE field='address') AS address_union,
          max(shared_mass) FILTER (WHERE field='address') AS address_shared,
          max(left_mass) FILTER (WHERE field='address') AS address_left,
          max(right_mass) FILTER (WHERE field='address') AS address_right
        FROM aggregate GROUP BY anchor,rid)
    SELECT j.anchor,j.entity_id,j.ln,j.la,j.rn,j.ra,j.retrieval,j.hits,j.right_source,
      j.log_lnf,j.log_laf,j.log_rnf,j.log_raf,j.log_rank,j.relative_retrieval,
      j.log_lexical_retrieval,j.log_character_retrieval,j.log_lexical_hits,j.log_character_hits,
      CASE WHEN coalesce(w.name_union,0)>0 THEN w.name_shared/w.name_union ELSE 0 END,
      CASE WHEN least(coalesce(w.name_left,0),coalesce(w.name_right,0))>0
        THEN w.name_shared/least(w.name_left,w.name_right) ELSE 0 END,
      CASE WHEN coalesce(w.name_left,0)>0 THEN w.name_shared/w.name_left ELSE 0 END,
      CASE WHEN coalesce(w.name_right,0)>0 THEN w.name_shared/w.name_right ELSE 0 END,
      CASE WHEN coalesce(w.address_union,0)>0 THEN w.address_shared/w.address_union ELSE 0 END,
      CASE WHEN least(coalesce(w.address_left,0),coalesce(w.address_right,0))>0
        THEN w.address_shared/least(w.address_left,w.address_right) ELSE 0 END,
      CASE WHEN coalesce(w.address_left,0)>0 THEN w.address_shared/w.address_left ELSE 0 END,
      CASE WHEN coalesce(w.address_right,0)>0 THEN w.address_shared/w.address_right ELSE 0 END
    FROM joined j LEFT JOIN pivoted w USING(anchor,rid)
    ORDER BY j.anchor,j.entity_id'''


def prepare_indexes(c, split):
    build_char_index(c, split)
    return ensure_token_idf_tables(c, split)


def materialize(db, out, partition=0, partitions=8, confirmation=False):
    if confirmation:
        raise ValueError('M001c must not consume a confirmation window')
    return materialize_v2(
        db,out,partition,partitions,confirmation=False,
        candidate_fn=fused_candidates,query_fn=pair_query,feature_names=V5_NAMES,
        index_fn=prepare_indexes,
    )


def score_rows(rows):
    from .v2 import compute_rows
    ids,x=compute_rows(rows)
    if x.shape[1]!=len(V5_NAMES):
        raise ValueError('V5 feature query/schema mismatch')
    return ids,x


def assert_prepared(c, split):
    return ensure_token_idf_tables(c, split)
