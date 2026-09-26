"""Candidate-fusion and matched-pool training for submission v3."""
import json
import shutil
from pathlib import Path

import modal
from modal_app import image,volume,_enable_native_features,SCRATCH,VOLUME_ROOT

image=image.add_local_python_source('modal_app')
app=modal.App('team517-v3')
ROOT=VOLUME_ROOT/'project/experiments/int003'
BASE_DB=VOLUME_ROOT/'project/artifacts/data.duckdb'
V3_DB=VOLUME_ROOT/'project/artifacts/data_v3.duckdb'


def copy_database():
    dest=SCRATCH/'artifacts/data_v3.duckdb'
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(V3_DB,dest)
    return dest


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=32768,timeout=3600)
def prepare_database():
    from ber.data import connect
    from ber.provenance import file_signature,source_file_sha256
    from ber.retrieval_v3 import build_char_index
    receipt=ROOT/'database_ready.json'
    identity={
        'version':2,
        'base_database':file_signature(BASE_DB),
        'retrieval_v3_sha256':source_file_sha256(build_char_index),
    }
    if receipt.exists() and V3_DB.exists():
        meta=json.loads(receipt.read_text())
        if meta.get('identity')==identity:
            return meta
        print('Rebuilding stale v3 prepared database',flush=True)
    work=SCRATCH/'artifacts/data_v3.duckdb'
    work.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(BASE_DB,work)
    c=connect(work)
    c.execute("SET memory_limit='20GB'")
    c.execute('SET threads=8')
    char_index_fingerprints={}
    for split in ('train','test'):
        char_index_fingerprints[split]=build_char_index(c,split)
        rows=c.execute(f'SELECT count(*) FROM {split}_char_index').fetchone()[0]
        print(f'{split} character postings: {rows:,}',flush=True)
    c.execute('CHECKPOINT')
    c.close()
    staging=V3_DB.with_suffix('.duckdb.tmp')
    shutil.copy2(work,staging)
    staging.replace(V3_DB)
    ROOT.mkdir(parents=True,exist_ok=True)
    meta={'version':2,'identity':identity,'source_bytes':BASE_DB.stat().st_size,
          'database_bytes':V3_DB.stat().st_size,
          'char_index_fingerprints':char_index_fingerprints,
          'target_index':'name character 3/4 grams, DF<=2000'}
    receipt.write_text(json.dumps(meta,indent=2),encoding='utf-8')
    volume.commit()
    return meta


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=16384,timeout=1800)
def retrieval_gate():
    from ber.data import connect
    from ber.experiment import fold
    from ber.blocking import build_index,candidates
    from ber.retrieval_v3 import build_char_index,fused_candidates,evaluate_table
    c=connect(copy_database())
    c.execute("SET memory_limit='12GB'")
    c.execute('SET threads=8')
    build_index(c,'train');build_char_index(c,'train')
    c.execute('''CREATE OR REPLACE TEMP TABLE dev30k AS SELECT * FROM train
        WHERE source=1 ORDER BY md5('sample517:'||entity_id) LIMIT 30000''')
    selected=[(i,) for (i,) in c.execute('SELECT entity_id FROM dev30k').fetchall()
              if fold(i)=='calibrate']
    c.execute('CREATE TEMP TABLE gate_ids(entity_id VARCHAR)')
    c.executemany('INSERT INTO gate_ids VALUES (?)',selected)
    c.execute('CREATE OR REPLACE TEMP TABLE gate_anchors AS SELECT d.* FROM dev30k d JOIN gate_ids USING(entity_id)')
    meta=[{'id':i,'country':co,'truth':t.split(',') if t else []}
          for i,co,t in c.execute('''SELECT a.entity_id,a.country,t.matches
          FROM gate_anchors a JOIN truth t ON a.entity_id=t.anchor''').fetchall()]
    candidates(c,'train','gate_anchors','gate_lexical',160)
    baseline=evaluate_table(c,'gate_lexical',meta)
    fused_candidates(c,'train','gate_anchors','gate_fused',160)
    changed=evaluate_table(c,'gate_fused',meta)
    result={'protocol':'Complete train target inventory; same 4389 calibration anchors and cap160; score-only rank fusion',
        'baseline':baseline,'fused':changed,
        'candidate_pair_recall_delta':changed['candidate_pair_recall']-baseline['candidate_pair_recall'],
        'oracle_delta':changed['blocking_oracle_macro_f0_5']-baseline['blocking_oracle_macro_f0_5']}
    (ROOT/'retrieval_gate.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    c.close();volume.commit()
    return result


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=32768,timeout=3600)
def make_features(partition:int,partitions:int=8,confirmation:bool=False,
                  comparison:bool=False):
    # Compile before importing ber: forked feature workers inherit ber.__path__.
    _enable_native_features()
    from ber.v2 import V2_NAMES
    from ber.v3 import V3_NAMES
    if comparison and not confirmation:
        raise ValueError('The baseline comparison is only for confirmation')
    section='comparison' if comparison else 'confirmation' if confirmation else 'features'
    out=ROOT/section/f'part{partition}'
    names=V2_NAMES if comparison else V3_NAMES
    if (out/'ready.json').exists():
        meta=json.loads((out/'ready.json').read_text())
        if meta['feature_names']!=names or meta['partitions']!=partitions or meta['partition']!=partition:
            raise ValueError('Stale or mismatched feature cache')
        return meta
    db=copy_database()
    if comparison:
        from ber.v2 import materialize
        result=materialize(db,out,partition,partitions,confirmation=True,
                           confirmation_start=45000)
    else:
        from ber.v3 import materialize
        result=materialize(db,out,partition,partitions,confirmation)
    volume.commit()
    return result


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=65536,gpu='L4',timeout=3600)
def train_model(depth:int=10):
    from ber.v2 import V2_NAMES,train
    from ber.v3 import V3_NAMES
    result=train(ROOT/'features',ROOT/f'depth{depth}',
        VOLUME_ROOT/'project/experiments/int002/depth10',depth=depth,
        feature_names=V3_NAMES,feature_version=3,
        baseline_feature_count=len(V2_NAMES),baseline_threshold=.6500000000000002,
        blocker='lexical+char-rrf160-average-tie-rank')
    volume.commit()
    return result


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=16384,timeout=1800)
def confirm_model(depth:int=10):
    import numpy as np
    from catboost import CatBoostClassifier
    from ber.v2 import V2_NAMES,load_parts,score_slices
    from ber.v3 import V3_NAMES
    from ber.experiment import mappings
    from ber.metrics import row_score
    from ber.predict import sha256

    x,y,g,t,meta=load_parts(ROOT/'confirmation',1,V3_NAMES)
    bx,by,bg,bt,bmeta=load_parts(ROOT/'comparison',1,V2_NAMES)
    if [m['id'] for m in meta]!=[m['id'] for m in bmeta]:
        raise ValueError('Baseline and v3 confirmation anchors disagree')
    folder=ROOT/f'depth{depth}'
    config=json.loads((folder/'model_config.json').read_text())
    model=CatBoostClassifier();model.load_model(str(folder/'mixed.cbm'))
    p=model.predict_proba(x,thread_count=8)[:,1]
    old=CatBoostClassifier()
    old.load_model(str(VOLUME_ROOT/'project/experiments/int002/depth10/mixed.cbm'))
    bp=old.predict_proba(bx,thread_count=8)[:,1]
    bp_fused=old.predict_proba(x[:,:len(V2_NAMES)],thread_count=8)[:,1]
    report={'protocol':'5000 anchors at hash positions 45001:50000, excluded from v2/v3 fitting and model selection; full-S1 swarm audits may have inspected labels',
        'config':config,'model_sha256':sha256(folder/'mixed.cbm'),
        'baseline_v2_original_pool':score_slices(bmeta,bg,bt,bp,'confirmation',.6500000000000002),
        'baseline_v2_fused_pool':score_slices(meta,g,t,bp_fused,'confirmation',.6500000000000002),
        'new':score_slices(meta,g,t,p,'confirmation',config['threshold'])}
    truth,pred,_=mappings(meta,g,t,p,range(len(meta)),config['threshold'])
    _,prior,_=mappings(bmeta,bg,bt,bp,range(len(bmeta)),.6500000000000002)
    delta=np.array([row_score(truth[k],pred[k])-row_score(truth[k],prior[k]) for k in truth])
    rng=np.random.default_rng(517)
    boot=np.array([rng.choice(delta,size=len(delta),replace=True).mean() for _ in range(2000)])
    report['paired_comparison']={'delta':float(delta.mean()),
        'bootstrap_95_interval':np.quantile(boot,[.025,.975]).tolist(),
        'improved_entities':int((delta>0).sum()),
        'regressed_entities':int((delta<0).sum()),'seed':517,'resamples':2000}
    (folder/'confirmation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    volume.commit()
    return report


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=32768,timeout=3600)
def score_partition(depth:int,partition:int,partitions:int=8):
    import threading
    _enable_native_features()
    from ber.predict import predict
    db=copy_database()
    out=VOLUME_ROOT/'project/output'/f'submission_v3_d{depth}_part{partition}of{partitions}'
    stop=threading.Event()
    def checkpoint():
        while not stop.wait(180):
            volume.commit()
    thread=threading.Thread(target=checkpoint,daemon=True)
    thread.start()
    try:
        predict(db,ROOT/f'depth{depth}',out,batch_size=10000,workers=8,
                query_batches=1,partition_index=partition,partition_count=partitions)
    finally:
        stop.set();thread.join(timeout=30);volume.commit()
    return str(out)


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=4,memory=16384,timeout=1800)
def merge_prediction(depth:int,partitions:int=8):
    from modal_app import merge_score
    return merge_score.local(f'submission_v3_d{depth}',partitions,160)


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=2,memory=4096,timeout=900)
def package_matching(depth:int):
    import gzip
    from ber.predict import sha256

    folder=VOLUME_ROOT/'project/output'/f'submission_v3_d{depth}'
    source=folder/'matching_results.tsv'
    receipt=json.loads((folder/'completion.json').read_text())
    if sha256(source)!=receipt['matching_sha256']:
        raise ValueError('Validated matching file checksum mismatch')
    target=folder/'matching_results.tsv.gz'
    with source.open('rb') as src,target.open('wb') as dest:
        with gzip.GzipFile(filename='',mode='wb',fileobj=dest,compresslevel=3,mtime=0) as compressed:
            shutil.copyfileobj(src,compressed,1024*1024)
    result={'matching_sha256':receipt['matching_sha256'],
            'compressed_sha256':sha256(target),'compressed_bytes':target.stat().st_size,
            'matching_bytes':source.stat().st_size}
    volume.commit()
    return result


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=1,memory=1024,timeout=300)
def matching_download_tail(depth:int,offset:int):
    source=VOLUME_ROOT/'project/output'/f'submission_v3_d{depth}'/'matching_results.tsv.gz'
    with source.open('rb') as stream:
        stream.seek(offset)
        remaining=stream.read()
    if len(remaining)>8*1024*1024:
        raise ValueError('Download the main body with the Modal Volume CLI first')
    return remaining


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=1,memory=1024,timeout=300)
def matching_download_chunk(depth:int,offset:int,length:int):
    if length<1 or length>4*1024*1024 or offset<0:
        raise ValueError('Invalid download range')
    source=VOLUME_ROOT/'project/output'/f'submission_v3_d{depth}'/'matching_results.tsv.gz'
    with source.open('rb') as stream:
        stream.seek(offset)
        chunk=stream.read(length)
    if len(chunk)!=length:
        raise ValueError('Remote compressed file is incomplete')
    return chunk


@app.local_entrypoint()
def main(action:str='prepare',depth:int=10):
    if action=='prepare':
        result=prepare_database.remote()
        Path('reports/int003_database.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    elif action=='retrieval':
        result=retrieval_gate.remote()
        Path('reports/int003_retrieval.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:result[k] for k in ('candidate_pair_recall_delta','oracle_delta')},indent=2))
    elif action=='train':
        prepare_database.remote()
        calls=[make_features.spawn(i) for i in range(8)]
        for i,call in enumerate(calls):
            receipt=call.get()
            print(f'Feature partition {i}: {receipt["anchors"]} anchors',flush=True)
        result=train_model.remote(depth)
        Path(f'reports/int003_depth{depth}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(f'Trained v3 depth {depth}',flush=True)
    elif action=='confirm':
        calls=[make_features.spawn(0,1,True,comparison) for comparison in (False,True)]
        for call in calls:
            print(f'Confirmation features: {call.get()["anchors"]} anchors',flush=True)
        result=confirm_model.remote(depth)
        Path(f'reports/int003_depth{depth}_confirmation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)
    elif action=='score':
        calls=[score_partition.spawn(depth,i) for i in range(8)]
        for call in calls:
            print(call.get(),flush=True)
        result=merge_prediction.remote(depth)
        Path(f'reports/int003_depth{depth}_export.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)
    elif action=='package':
        result=package_matching.remote(depth)
        Path(f'reports/int003_depth{depth}_download.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)
    elif action=='download':
        import hashlib
        dest=Path(f'output/submission_v3_d{depth}')
        dest.mkdir(parents=True,exist_ok=True)
        receipt=json.loads(Path(f'reports/int003_depth{depth}_download.json').read_text())
        temporary=dest/'matching_results.tsv.gz.tmp'
        step=4*1024*1024
        with temporary.open('wb') as stream:
            for offset in range(0,receipt['compressed_bytes'],step):
                size=min(step,receipt['compressed_bytes']-offset)
                stream.write(matching_download_chunk.remote(depth,offset,size))
                print(f'Downloaded {offset+size:,}/{receipt["compressed_bytes"]:,} bytes',flush=True)
        with temporary.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=receipt['compressed_sha256']:
                raise ValueError('Chunked transfer checksum mismatch')
        temporary.replace(dest/'matching_results.tsv.gz')
        print('Compressed transfer SHA256 PASS',flush=True)
    elif action=='resume-download':
        import gzip
        import hashlib
        dest=Path(f'output/submission_v3_d{depth}')
        compressed=dest/'matching_results.tsv.gz'
        receipt=json.loads(Path(f'reports/int003_depth{depth}_download.json').read_text())
        offset=compressed.stat().st_size
        if offset>receipt['compressed_bytes']:
            raise ValueError('Local compressed file exceeds the remote file')
        if offset<receipt['compressed_bytes']:
            with compressed.open('ab') as stream:
                stream.write(matching_download_tail.remote(depth,offset))
        with compressed.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=receipt['compressed_sha256']:
                raise ValueError('Compressed download checksum mismatch')
        temporary=dest/'matching_results.tsv.tmp'
        with gzip.open(compressed,'rb') as src,temporary.open('wb') as out:
            shutil.copyfileobj(src,out,1024*1024)
        with temporary.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=receipt['matching_sha256']:
                raise ValueError('Decompressed matching checksum mismatch')
        target=dest/'matching_results.tsv'
        temporary.replace(target)
        print(f'PASS: {target}; SHA256 {receipt["matching_sha256"]}')
    else:
        raise ValueError('Unknown action')
