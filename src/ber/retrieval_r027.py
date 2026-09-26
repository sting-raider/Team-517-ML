"""Number-conditioned character rescue on top of the bounded v3 blocker."""

from .retrieval_v3 import build_char_index, fused_candidates


def build_number_char_index(c, split):
    """Index name-character postings by each address number and country.

    The existing character key already includes country. The composite key
    avoids a full scan of character postings when an anchor has an address
    number, while retaining every distinct number rather than assuming it is
    the first one in every vendor's address format.
    """
    ready = c.execute('''SELECT count(*) FROM information_schema.tables
        WHERE table_name=?''', [f'{split}_number_char_index']).fetchone()[0]
    if ready:
        print(f'Reusing {split} number-character index', flush=True)
        return
    build_char_index(c, split)
    c.execute(f'''CREATE OR REPLACE TEMP TABLE r027_numbers AS
        SELECT rowid rid,list_distinct(regexp_extract_all(a,'[0-9]+')) nums
        FROM {split} WHERE source>1 AND regexp_extract(a,'[0-9]+')<>''''')
    c.execute(f'''CREATE TABLE {split}_number_char_index AS
        SELECT p.rid,hash(num,p.key) AS key,p.freq
        FROM {split}_char_index p JOIN r027_numbers n USING(rid),
             unnest(n.nums) u(num)''')
    c.execute('DROP TABLE r027_numbers')
    print(f'Built {split} number-character index', flush=True)


def number_char_candidates(c, split, anchors, result='number_char_candidates', cap=32):
    """Retrieve only bounded name-character matches sharing an address number."""
    c.execute(f'''CREATE OR REPLACE TEMP TABLE r027_number_query AS
        SELECT q.anchor,hash(num,q.key) AS key
        FROM char_query q JOIN {anchors} a ON a.entity_id=q.anchor,
             unnest(list_distinct(regexp_extract_all(a.a,'[0-9]+'))) u(num)''')
    c.execute(f'''CREATE OR REPLACE TEMP TABLE {result} AS
        WITH hits AS (
          SELECT q.anchor,p.rid,sum(ln(10000001.0/p.freq))::FLOAT retrieval,
                 count(*)::SMALLINT hits
          FROM r027_number_query q JOIN {split}_number_char_index p USING(key)
          GROUP BY q.anchor,p.rid HAVING count(*)>=2)
        SELECT h.* FROM hits h JOIN {split} t ON t.rowid=h.rid
        QUALIFY row_number() OVER(PARTITION BY h.anchor
            ORDER BY h.retrieval DESC,t.entity_id)<={int(cap)}''')


def fused_candidates_r027(c, split, anchors, result, cap=160):
    """Union v3 and number-gated character candidates before final cap."""
    fused_candidates(c, split, anchors, 'r027_baseline', cap)
    number_char_candidates(c, split, anchors, 'r027_number_char', 32)
    c.execute(f'''CREATE OR REPLACE TABLE {result} AS
        WITH weighted AS (
          SELECT anchor,rid,retrieval::FLOAT weight FROM r027_baseline
          UNION ALL
          SELECT anchor,rid,(0.5/(60+rank() OVER(PARTITION BY anchor
                 ORDER BY retrieval DESC)))::FLOAT weight
          FROM r027_number_char), scored AS (
          SELECT anchor,rid,sum(weight)::FLOAT retrieval
          FROM weighted GROUP BY anchor,rid)
        SELECT s.anchor,s.rid,s.retrieval,
          (coalesce(b.base_hits,0)+greatest(coalesce(b.char_hits,0),coalesce(n.hits,0)))::SMALLINT hits,
          coalesce(b.base_retrieval,0)::FLOAT base_retrieval,
          greatest(coalesce(b.char_retrieval,0),coalesce(n.retrieval,0))::FLOAT char_retrieval,
          coalesce(b.base_hits,0)::SMALLINT base_hits,
          greatest(coalesce(b.char_hits,0),coalesce(n.hits,0))::SMALLINT char_hits
        FROM scored s JOIN {split} t ON t.rowid=s.rid
        LEFT JOIN r027_baseline b ON b.anchor=s.anchor AND b.rid=s.rid
        LEFT JOIN r027_number_char n ON n.anchor=s.anchor AND n.rid=s.rid
        QUALIFY row_number() OVER(PARTITION BY s.anchor
            ORDER BY s.retrieval DESC,t.entity_id)<={int(cap)}''')
