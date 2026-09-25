"""Complementary character retrieval and source-frequency experiments."""
import json
import time
from pathlib import Path
from .blocking import init_macros,candidates as lexical_candidates
from .data import connect
from .experiment import fold
from .metrics import evaluate


def build_source_index(c,split):
    init_macros(c)
    c.execute(f'''CREATE OR REPLACE TABLE {split}_sf_raw AS
        SELECT rowid AS rid,source,hash(country,source,k) AS key
        FROM {split},unnest(block_keys(n,a)) u(k) WHERE source>1 AND k IS NOT NULL''')
    c.execute(f'''CREATE OR REPLACE TABLE {split}_sf_freq AS
        SELECT key,count(*)::INTEGER freq FROM {split}_sf_raw GROUP BY key''')
    c.execute(f'''CREATE OR REPLACE TABLE {split}_sf_index AS
        SELECT r.rid,r.key,f.freq FROM {split}_sf_raw r JOIN {split}_sf_freq f USING(key)
        WHERE f.freq<=1000''')
    c.execute(f'DROP TABLE {split}_sf_raw')


def source_candidates(c,split,anchors,result,cap):
    c.execute(f'''CREATE OR REPLACE TEMP TABLE sf_query AS
        SELECT entity_id AS anchor,s.source,hash(country,s.source,k) AS key,left(k,2) AS kind,
          CASE left(k,2) WHEN 'n:' THEN 50.0 WHEN 'a:' THEN 40.0 WHEN 'w:' THEN 0.0 ELSE 8.0 END AS bonus,
          f.freq,k
        FROM {anchors} CROSS JOIN (VALUES(2),(3)) s(source),unnest(block_keys(n,a)) u(k)
        JOIN {split}_sf_freq f ON f.key=hash(country,s.source,k)
        WHERE k IS NOT NULL AND f.freq<=1000
        QUALIFY kind IN ('n:','a:','h:','z:') OR row_number() OVER(
          PARTITION BY entity_id,s.source,kind ORDER BY f.freq,k)<=4''')
    c.execute(f'''CREATE OR REPLACE TABLE {result} AS
        WITH hits AS (SELECT q.anchor,r.rid,sum(q.bonus+ln(10000001.0/r.freq))::FLOAT retrieval,
          count(*)::SMALLINT hits FROM sf_query q JOIN {split}_sf_index r USING(key) GROUP BY q.anchor,r.rid)
        SELECT h.* FROM hits h JOIN {split} r ON h.rid=r.rowid
        QUALIFY row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC,r.entity_id)<={int(cap)}''')


def build_char_index(c,split):
    c.execute('''CREATE OR REPLACE MACRO name_grams(n) AS list_distinct(list_concat(
        list_transform(range(1,greatest(1,length(replace(n,' ',''))-1)),i->'c3:'||substr(replace(n,' ',''),i,3)),
        list_transform(range(1,greatest(1,length(replace(n,' ',''))-2)),i->'c4:'||substr(replace(n,' ',''),i,4))))''')
    c.execute(f'''CREATE OR REPLACE TABLE {split}_char_raw AS
        SELECT rowid rid,hash(country,k) AS key FROM {split},unnest(name_grams(n)) u(k) WHERE source>1''')
    c.execute(f'''CREATE OR REPLACE TABLE {split}_char_freq AS
        SELECT key,count(*)::INTEGER freq FROM {split}_char_raw GROUP BY key''')
    c.execute(f'''CREATE OR REPLACE TABLE {split}_char_index AS
        SELECT r.rid,r.key,f.freq FROM {split}_char_raw r JOIN {split}_char_freq f USING(key) WHERE f.freq<=2000''')
    c.execute(f'DROP TABLE {split}_char_raw')


def char_candidates(c,split,anchors,result,cap=64):
    c.execute(f'''CREATE OR REPLACE TEMP TABLE char_query AS
        SELECT entity_id anchor,hash(country,k) AS key,f.freq,left(k,3) kind,k
        FROM {anchors},unnest(name_grams(n)) u(k)
        JOIN {split}_char_freq f ON f.key=hash(country,k) WHERE f.freq<=2000
        QUALIFY row_number() OVER(PARTITION BY entity_id,kind ORDER BY f.freq,k)<=6''')
    c.execute(f'''CREATE OR REPLACE TABLE {result} AS
        WITH hits AS (SELECT q.anchor,r.rid,sum(ln(10000001.0/r.freq))::FLOAT retrieval,
          count(*)::SMALLINT hits FROM char_query q JOIN {split}_char_index r USING(key)
          GROUP BY q.anchor,r.rid HAVING count(*)>=2)
        SELECT h.* FROM hits h JOIN {split} r ON h.rid=r.rowid
        QUALIFY row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC,r.entity_id)<={int(cap)}''')


def evaluate_table(c,table,meta):
    truth={m['id']:m['truth'] for m in meta}; cand={k:set() for k in truth}
    for anchor,target in c.execute(f'SELECT p.anchor,r.entity_id FROM {table} p JOIN train r ON p.rid=r.rowid').fetchall():
        cand[anchor].add(target)
    oracle={k:set(truth[k])&cand[k] for k in truth}
    result=evaluate(truth,oracle,cand)
    result['mean_candidates']=sum(map(len,cand.values()))/len(cand)
    result['countries']={}
    for country in sorted({m['country'] for m in meta}):
        ct={m['id']:m['truth'] for m in meta if m['country']==country}
        result['countries'][country]=evaluate(ct,oracle,cand)
    return result


def experiment(db,out):
    c=connect(db);c.execute("SET memory_limit='20GB'");c.execute('SET threads=8')
    c.execute('''CREATE OR REPLACE TEMP TABLE dev30k AS SELECT * FROM train WHERE source=1
        ORDER BY md5('sample517:'||entity_id) LIMIT 30000''')
    ids=[(i,) for (i,) in c.execute('SELECT entity_id FROM dev30k').fetchall() if fold(i)=='calibrate']
    c.execute('CREATE TEMP TABLE cal_ids(entity_id VARCHAR)');c.executemany('INSERT INTO cal_ids VALUES (?)',ids)
    c.execute('CREATE OR REPLACE TEMP TABLE cal_anchors AS SELECT d.* FROM dev30k d JOIN cal_ids USING(entity_id)')
    meta=[{'id':i,'country':co,'truth':t.split(',') if t else []} for i,co,t in c.execute('''
        SELECT a.entity_id,a.country,t.matches FROM cal_anchors a JOIN truth t ON a.entity_id=t.anchor''').fetchall()]
    report={'protocol':'Same 4389 calibration anchors; complete train S2/S3 inventory; labels used only for evaluation','metrics':{},'seconds':{}}
    if len(meta)!=4389:
        raise ValueError('Unexpected calibration universe')
    started=time.time()
    lexical_candidates(c,'train','cal_anchors','base160',160)
    report['metrics']['base160']=evaluate_table(c,'base160',meta)
    if abs(report['metrics']['base160']['candidate_pair_recall']-.9253076721654884)>1e-12:
        raise ValueError('Baseline retrieval reproduction failed')
    print('Baseline reproduced',flush=True)
    phase=time.time();build_source_index(c,'train')
    source_candidates(c,'train','cal_anchors','source160',160)
    report['metrics']['source160']=evaluate_table(c,'source160',meta)
    report['seconds']['source_index_and_query']=time.time()-phase
    print('Source frequency',json.dumps(report['metrics']['source160']),flush=True)
    phase=time.time();build_char_index(c,'train')
    char_candidates(c,'train','cal_anchors','char64',64)
    report['metrics']['char64']=evaluate_table(c,'char64',meta)
    report['seconds']['char_index_and_query']=time.time()-phase
    for base in ('base160','source160'):
        c.execute(f'''CREATE OR REPLACE TEMP TABLE union_pool AS
            SELECT anchor,rid,max(retrieval) retrieval,max(hits) hits
            FROM (SELECT * FROM {base} UNION ALL SELECT * FROM char64) GROUP BY anchor,rid''')
        report['metrics'][base+'_char_union']=evaluate_table(c,'union_pool',meta)
        c.execute(f'''CREATE OR REPLACE TEMP TABLE fused AS
            WITH ranks AS (
              SELECT p.anchor,p.rid,1.0/(60+row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC,r.entity_id)) weight
              FROM {base} p JOIN train r ON p.rid=r.rowid
              UNION ALL
              SELECT p.anchor,p.rid,0.5/(60+row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC,r.entity_id)) weight
              FROM char64 p JOIN train r ON p.rid=r.rowid), summed AS (
                SELECT anchor,rid,sum(weight) score FROM ranks GROUP BY anchor,rid)
            SELECT s.* FROM summed s JOIN train r ON s.rid=r.rowid
            QUALIFY row_number() OVER(PARTITION BY anchor ORDER BY score DESC,r.entity_id)<=160''')
        report['metrics'][base+'_char_rrf160']=evaluate_table(c,'fused',meta)
    report['seconds']['total']=time.time()-started
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(report,indent=2),encoding='utf-8')
    c.close();return report
