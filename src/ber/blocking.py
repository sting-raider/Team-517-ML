"""Auditable bounded multi-pass lexical retrieval over the full record inventory."""
import argparse
import time
from pathlib import Path
from .data import connect


def init_macros(c):
    c.execute(r"""CREATE OR REPLACE MACRO address_words(a) AS
        list_filter(string_split(a,' '), x->len(x)>=3 AND NOT regexp_full_match(x,'[0-9]+')
        AND x NOT IN ('road','street','avenue','drive','lane','floor','near','opposite','the','and','unit','plot','no'))""")
    c.execute(r"""CREATE OR REPLACE MACRO block_keys(n,a) AS list_distinct(list_concat(
        [CASE WHEN n<>'' THEN 'n:'||replace(n,' ','') END,
         CASE WHEN a<>'' THEN 'a:'||replace(a,' ','') END,
         CASE WHEN len(n)>=4 AND regexp_extract(a,'[0-9]+')<>''
              THEN 'h:'||left(replace(n,' ',''),6)||':'||regexp_extract(a,'[0-9]+') END,
         CASE WHEN len(n)>=4 AND regexp_extract(a,'[0-9]+[^0-9]*$',0)<>''
              THEN 'z:'||left(replace(n,' ',''),6)||':'||regexp_extract(a,'([0-9]+)[^0-9]*$',1) END],
        list_transform(list_filter(string_split(n,' '), x->len(x)>=3), x->'w:'||x),
        list_transform(address_words(a), x->'u:'||x),
        list_transform(range(1,len(address_words(a))), i->'v:'||
            least(address_words(a)[i],address_words(a)[i+1])||':'||greatest(address_words(a)[i],address_words(a)[i+1])),
        CASE WHEN regexp_extract(a,'[0-9]+')<>'' THEN
            list_transform(address_words(a), x->'d:'||regexp_extract(a,'[0-9]+')||':'||x) ELSE [] END))""")


def build_index(c, split):
    init_macros(c)
    c.execute('CREATE TABLE IF NOT EXISTS index_versions (split VARCHAR PRIMARY KEY, version INTEGER)')
    version=c.execute('SELECT version FROM index_versions WHERE split=?',[split]).fetchone()
    if version and version[0]==2:
        print(f'Reusing {split} retrieval index', flush=True)
        return
    start=time.time()
    # Hashes are retrieval keys only, never ML features or matching evidence.
    c.execute(f"""CREATE OR REPLACE TABLE {split}_rawkeys AS
        SELECT rowid AS rid, hash(country,k) AS key FROM {split},
        unnest(block_keys(n,a)) AS u(k) WHERE source>1 AND k IS NOT NULL""")
    print(f'{split}: raw keys built in {time.time()-start:.1f}s',flush=True)
    c.execute(f"""CREATE OR REPLACE TABLE {split}_freq AS
        SELECT key,count(*)::INTEGER AS freq FROM {split}_rawkeys GROUP BY key""")
    c.execute(f"""CREATE OR REPLACE TABLE {split}_index AS SELECT r.rid,r.key,f.freq
        FROM {split}_rawkeys r JOIN {split}_freq f USING(key) WHERE f.freq<=1000""")
    c.execute(f'DROP TABLE {split}_rawkeys')
    c.execute('INSERT OR REPLACE INTO index_versions VALUES (?,2)',[split])
    c.execute('CHECKPOINT')
    print(f'{split}: index ready in {time.time()-start:.1f}s',flush=True)


def candidates(c, split, anchor_table='anchors', result='candidates', cap=80):
    init_macros(c)
    # Full-name/address/numeric keys plus four rarest eligible name tokens.
    c.execute(f"""CREATE OR REPLACE TEMP TABLE query_keys AS
        SELECT entity_id AS anchor, hash(country,k) AS key,
        CASE left(k,2) WHEN 'n:' THEN 50.0 WHEN 'a:' THEN 40.0
            WHEN 'w:' THEN 0.0 ELSE 8.0 END AS bonus,
        left(k,2) AS kind, f.freq
        FROM {anchor_table}, unnest(block_keys(n,a)) AS u(k)
        JOIN {split}_freq f ON f.key=hash(country,k)
        WHERE k IS NOT NULL AND f.freq<=1000
        QUALIFY kind IN ('n:','a:','h:','z:') OR row_number() OVER(PARTITION BY entity_id,kind ORDER BY f.freq,k)<=4""")
    c.execute(f"""CREATE OR REPLACE TABLE {result} AS
        WITH hits AS (SELECT q.anchor,r.rid,sum(q.bonus+ln(10000001.0/r.freq))::FLOAT AS retrieval,
            count(*)::SMALLINT AS hits FROM query_keys q JOIN {split}_index r USING(key) GROUP BY q.anchor,r.rid)
        SELECT h.* FROM hits h JOIN {split} t ON h.rid=t.rowid
        QUALIFY row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC,t.entity_id)<={int(cap)}""")


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=Path('artifacts/data.duckdb'))
    p.add_argument('--split',choices=['train','test'],default='train')
    p.add_argument('--anchors',type=int,default=30000)
    p.add_argument('--cap',type=int,default=80)
    a=p.parse_args()
    c=connect(a.db)
    build_index(c,a.split)
    c.execute(f"""CREATE OR REPLACE TABLE anchors AS SELECT * FROM {a.split}
        WHERE source=1 ORDER BY md5('sample517:'||entity_id) LIMIT {a.anchors}""")
    candidates(c,a.split,cap=a.cap)
    print(c.execute('SELECT count(*),count(DISTINCT anchor) FROM candidates').fetchone(),flush=True)
    c.close()


if __name__=='__main__':
    main()
