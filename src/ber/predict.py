"""Bounded-memory, resumable inference and exact candidate export."""
import argparse
import hashlib
import json
import time
from itertools import groupby
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from catboost import CatBoostClassifier
from .blocking import build_index,candidates
from .data import connect
from .features import batch_features,FEATURE_NAMES
from .shortlist import shortlist_rows


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def prepare_groups(payload):
    groups,cap=payload
    selected=[r for group in groups for r in shortlist_rows(group,cap)]
    if selected and len(selected[0])>9:
        from .v2 import compute_rows
        return compute_rows(selected)
    return [(r[0],r[1]) for r in selected],batch_features([r[2:] for r in selected])


def score_batch(c,model,threshold,split,anchor_table,candidate_table,shortlist_cap=None,executor=None,feature_version=1):
    anchor_ids=[r[0] for r in c.execute(f'SELECT entity_id FROM {anchor_table} ORDER BY entity_id').fetchall()]
    selected={k:[] for k in anchor_ids}
    considered={k:[] for k in anchor_ids}
    if feature_version==4:
        from .v4 import pair_query
        query=pair_query(split,anchor_table,candidate_table)
    elif feature_version==3:
        from .v3 import pair_query
        query=pair_query(split,anchor_table,candidate_table)
    elif feature_version==2:
        from .v2 import pair_query
        query=pair_query(split,anchor_table,candidate_table)
    else:
        query=f'''SELECT p.anchor,r.entity_id,l.n,l.a,r.n,r.a,p.retrieval,p.hits,r.source
        FROM {candidate_table} p JOIN {anchor_table} l ON p.anchor=l.entity_id
        JOIN {split} r ON p.rid=r.rowid ORDER BY p.anchor,r.entity_id'''
    c.execute(query)
    def all_records():
        while records:=c.fetchmany(20000):
            yield from records
    def grouped_batches():
        pending=[]
        for _,group in groupby(all_records(),key=lambda r:r[0]):
            pending.append(list(group))
            if len(pending)>=250:
                yield pending,shortlist_cap
                pending=[]
        if pending:
            yield pending,shortlist_cap
    def feature_batches():
        if executor is None:
            for payload in grouped_batches():
                yield prepare_groups(payload)
        else:
            pending=deque()
            for payload in grouped_batches():
                if len(pending)>=8:
                    yield pending.popleft().result()
                pending.append(executor.submit(prepare_groups,payload))
            while pending:
                yield pending.popleft().result()
    for records,x in feature_batches():
        probabilities=model.predict_proba(x,thread_count=6)[:,1]
        for r,p in zip(records,probabilities):
            considered[r[0]].append(r[1])
            if p>=threshold:
                selected[r[0]].append(r[1])
    return selected,considered


def write_tsv(path,mapping,column):
    temp=path.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8',newline='') as f:
        f.write(f'source1_entity_id\t{column}\n')
        for k,values in mapping.items():
            f.write(k+'\t'+','.join(values)+'\n')
    temp.replace(path)


def predict(db,model_dir,out,batch_size=10000,limit=None,cap=None,workers=4,query_batches=5,
            partition_index=0,partition_count=1):
    if batch_size<1 or workers<1 or query_batches<1:
        raise ValueError('Batch and worker counts must be positive')
    if partition_count<1 or not 0<=partition_index<partition_count:
        raise ValueError('Invalid partition index/count')
    config=json.loads((model_dir/'model_config.json').read_text())
    feature_version=config.get('feature_version',1)
    expected_features=FEATURE_NAMES
    if feature_version==4:
        from .v4 import V4_NAMES,build_indexes
        from .v2 import frequency_tables
        from .retrieval_v3 import fused_candidates
        expected_features=V4_NAMES
    elif feature_version==3:
        from .v3 import V3_NAMES
        from .v2 import frequency_tables
        from .retrieval_v3 import build_char_index,fused_candidates
        expected_features=V3_NAMES
    elif feature_version==2:
        from .v2 import V2_NAMES,frequency_tables
        expected_features=V2_NAMES
    if config['feature_names']!=expected_features:
        raise ValueError('Feature schema does not match the saved model')
    cap=cap or config['candidate_cap']
    model=CatBoostClassifier()
    model.load_model(str(model_dir/'mixed.cbm'))
    out.mkdir(parents=True,exist_ok=True)
    identity={'model_sha256':sha256(model_dir/'mixed.cbm'),'config':config,'cap':cap,
              'batch_size':batch_size,'limit':limit,'database':str(db.resolve()),
              'index_version':4 if feature_version==4 else 3 if feature_version==3 else 2,
              'partition_index':partition_index,'partition_count':partition_count}
    manifest=out/'run.json'
    if manifest.exists() and json.loads(manifest.read_text())!=identity:
        raise ValueError('Output folder belongs to a different run; choose a new --out directory')
    manifest.write_text(json.dumps(identity,indent=2),encoding='utf-8')
    c=connect(db)
    build_index(c,'test')
    if feature_version in (2,3,4):
        frequency_tables(c,'test')
    if feature_version==4:
        build_indexes(c,'test')
    elif feature_version==3:
        build_char_index(c,'test')
    sql='SELECT *,row_number() OVER(ORDER BY entity_id) AS seq FROM test WHERE source=1'
    if partition_count>1:
        sql+=f' AND hash(entity_id)%{partition_count}={partition_index}'
    if limit:
        sql+=' ORDER BY entity_id LIMIT '+str(int(limit))
    c.execute('CREATE OR REPLACE TABLE inference_anchors AS '+sql)
    total=c.execute('SELECT count(*) FROM inference_anchors').fetchone()[0]
    paths=[]
    start=time.time()
    executor=ProcessPoolExecutor(max_workers=workers) if workers>1 else None
    step=batch_size*query_batches
    for offset in range(0,total,step):
        batch_shards=[]
        for suboffset in range(offset,min(offset+step,total),batch_size):
            shard=out/'shards'/f'{suboffset:08d}'
            shard.mkdir(parents=True,exist_ok=True)
            paths.append(shard)
            done=shard/'done.json'
            if done.exists():
                proof=json.loads(done.read_text())
                if not all(sha256(shard/name)==digest for name,digest in proof.items()):
                    raise ValueError(f'Shard checksum mismatch: {shard}')
            batch_shards.append((shard,done.exists()))
        if all(complete for _,complete in batch_shards):
            continue
        phase_start=time.time()
        c.execute(f'''CREATE OR REPLACE TEMP TABLE batch_anchors AS SELECT * FROM inference_anchors
            WHERE seq>{offset} AND seq<={offset+step}''')
        candidate_fn=fused_candidates if feature_version in (3,4) else candidates
        candidate_fn(c,'test','batch_anchors','batch_candidates',cap)
        blocking_seconds=time.time()-phase_start
        matched,considered=score_batch(c,model,config['threshold'],'test','batch_anchors','batch_candidates',config.get('shortlist_cap'),executor,feature_version)
        ordered_ids=list(matched)
        for i,(shard,complete) in enumerate(batch_shards):
            if complete:
                continue
            ids=ordered_ids[i*batch_size:(i+1)*batch_size]
            write_tsv(shard/'matching_results.tsv',{k:matched[k] for k in ids},'matched_entity_ids')
            write_tsv(shard/'candidate_pairs.tsv',{k:considered[k] for k in ids},'candidate_entity_ids')
            proof={name:sha256(shard/name) for name in ('matching_results.tsv','candidate_pairs.tsv')}
            (shard/'done.json').write_text(json.dumps(proof),encoding='utf-8')
        print(f'{min(offset+step,total):,}/{total:,} anchors; elapsed {time.time()-start:.1f}s; blocking {blocking_seconds:.1f}s, scoring/export {time.time()-phase_start-blocking_seconds:.1f}s',flush=True)
    if executor is not None:
        executor.shutdown()
    for name in ('matching_results.tsv','candidate_pairs.tsv'):
        temp=out/(name+'.tmp')
        with temp.open('wb') as dest:
            for i,shard in enumerate(paths):
                with (shard/name).open('rb') as source:
                    header=source.readline()
                    if i==0:
                        dest.write(header)
                    for chunk in iter(lambda:source.read(1024*1024),b''):
                        dest.write(chunk)
        temp.replace(out/name)
    c.close()
    print(f'Completed {total:,} anchors in {out}',flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=Path('artifacts/data.duckdb'))
    p.add_argument('--model',type=Path,default=Path('artifacts/address_baseline'))
    p.add_argument('--out',type=Path,default=Path('output/baseline'))
    p.add_argument('--batch-size',type=int,default=10000)
    p.add_argument('--limit',type=int)
    p.add_argument('--cap',type=int)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--query-batches',type=int,default=5,help='Group output shards into larger retrieval queries')
    p.add_argument('--partition-index',type=int,default=0)
    p.add_argument('--partition-count',type=int,default=1)
    a=p.parse_args()
    predict(a.db,a.model,a.out,a.batch_size,a.limit,a.cap,a.workers,a.query_batches,
            a.partition_index,a.partition_count)


if __name__=='__main__':
    main()
