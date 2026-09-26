"""Resumable 32-candidate test pipeline with ANN blocking and cross-encoder matching."""
import json
import shutil
import time
from pathlib import Path

import numpy as np

from .data import connect
from .dense_training import serialize
from .predict import sha256,write_tsv
from .retrieval_v3 import fused_candidates


def score_partition(db, dense_root, encoder_path, cross_path, out,
                    country, partition, partitions, threshold,
                    batch_size=5000, checkpoint=None,anchor_limit=None,
                    cat_path=None,dense_prior=-2.):
    import faiss
    import torch
    import torch.nn.functional as F
    from catboost import CatBoostClassifier
    from transformers import AutoModel,AutoModelForSequenceClassification,AutoTokenizer

    if country not in ('France','India','US') or not 0<=partition<partitions:
        raise ValueError('Invalid country or partition')
    if not .01<=threshold<=.999:
        raise ValueError('Invalid calibrated cross-encoder threshold')
    started=time.monotonic()
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    config={'country':country,'partition':partition,'partitions':partitions,
            'threshold':threshold,'dense_prior':dense_prior if cat_path is not None else None,
            'matcher':'catboost_plus_cross' if cat_path is not None else 'cross_only',
            'anchor_limit':anchor_limit,'candidate_cap':32,'dense_slots':16,
            'base_cap':160,'base_scored_cap':32,'nprobe':64}
    config_path=out/'run_config.json'
    if config_path.exists() and json.loads(config_path.read_text())!=config:
        raise ValueError('Stale neural prediction shard/config mismatch')
    config_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    c=connect(db)
    c.execute("SET memory_limit='20GB'")
    c.execute('SET threads=8')
    if cat_path is not None:
        from .v2 import frequency_tables
        from .v3 import pair_query,score_rows
        frequency_tables(c,'test')
        cat=CatBoostClassifier()
        cat.load_model(str(cat_path))
    c.execute('''CREATE OR REPLACE TABLE neural_anchors AS SELECT *,
        row_number() OVER(ORDER BY entity_id) seq FROM test
        WHERE source=1 AND country=? AND hash(entity_id)%?=?''',
        [country,partitions,partition])
    if anchor_limit is not None:
        c.execute('''CREATE OR REPLACE TABLE neural_anchors AS
            SELECT * FROM neural_anchors WHERE seq<=?''',[anchor_limit])
    total=c.execute('SELECT count(*) FROM neural_anchors').fetchone()[0]
    if total<10000 and anchor_limit is None:
        raise ValueError('Unexpectedly small S1 test partition')
    torch.set_num_threads(4)
    tokenizer=AutoTokenizer.from_pretrained(encoder_path)
    encoder=AutoModel.from_pretrained(encoder_path).eval().cuda()
    pair_tokenizer=AutoTokenizer.from_pretrained(cross_path)
    matcher=AutoModelForSequenceClassification.from_pretrained(cross_path).eval().cuda()
    faiss.omp_set_num_threads(8)
    indexes=[]
    for part in range(4):
        path=Path(dense_root)/country/f'part{part}'/'ivfsq8.faiss'
        index=faiss.read_index(str(path))
        index.nprobe=64
        indexes.append(index)
    def embed(batch):
        vectors=np.empty((len(batch),encoder.config.hidden_size),np.float32)
        with torch.inference_mode():
            for start in range(0,len(batch),512):
                rows=batch[start:start+512]
                inputs=tokenizer([serialize(n,a) for _,n,a in rows],padding=True,
                                 truncation=True,max_length=128,return_tensors='pt').to('cuda')
                with torch.autocast('cuda',dtype=torch.bfloat16):
                    hidden=encoder(**inputs).last_hidden_state
                    mask=inputs['attention_mask'].unsqueeze(-1)
                    val=F.normalize((hidden.float()*mask).sum(1)/mask.sum(1).clamp_min(1),dim=1)
                vectors[start:start+len(rows)]=val.cpu().numpy()
        return vectors
    folders=[]
    for offset in range(0,total,batch_size):
        shard=out/'shards'/f'{offset:08d}'
        shard.mkdir(parents=True,exist_ok=True)
        folders.append(shard)
        done=shard/'done.json'
        if done.exists():
            proof=json.loads(done.read_text())
            if all(sha256(shard/name)==digest for name,digest in proof.items()):
                continue
            raise ValueError(f'Corrupted completed shard: {shard}')
        c.execute('''CREATE OR REPLACE TEMP TABLE batch_anchors AS
            SELECT * FROM neural_anchors WHERE seq>? AND seq<=?''',
            [offset,offset+batch_size])
        anchors=c.execute('''SELECT entity_id,business_name,business_address
            FROM batch_anchors ORDER BY entity_id''').fetchall()
        if not anchors:
            raise ValueError('Empty nonfinal anchor batch')
        # Both channels are bounded before cross-encoder scoring. The union is
        # dense top 16 followed by the highest v3 fused lexical/char records.
        fused_candidates(c,'test','batch_anchors','neural_base160',160)
        c.execute('''CREATE OR REPLACE TEMP TABLE neural_base32 AS
            SELECT p.* FROM neural_base160 p JOIN test t ON p.rid=t.rowid
            QUALIFY row_number() OVER(PARTITION BY p.anchor
                ORDER BY p.retrieval DESC,t.entity_id)<=32''')
        vectors=embed(anchors)
        results=[index.search(vectors,16) for index in indexes]
        selected_anchors=[];selected_rowids=[];selected_scores=[]
        for j,(anchor,_,_) in enumerate(anchors):
            ranked=sorted(((float(dist[j,k]),int(rid[j,k]))
                           for dist,rid in results for k in range(16)
                           if rid[j,k]>=0),reverse=True)
            seen=set()
            for similarity,rowid in ranked:
                if rowid not in seen:
                    selected_anchors.append(anchor)
                    selected_rowids.append(rowid)
                    selected_scores.append(similarity)
                    seen.add(rowid)
                if len(seen)==16:
                    break
        c.execute('''CREATE OR REPLACE TEMP TABLE neural_dense AS
            SELECT unnest(?) AS anchor,unnest(?) AS rid,unnest(?) AS similarity''',
            [selected_anchors,selected_rowids,selected_scores])
        c.execute('''CREATE OR REPLACE TEMP TABLE neural_candidates AS
            WITH raw AS (
                SELECT anchor,rid,0 priority,similarity ranking FROM neural_dense
                UNION ALL
                SELECT anchor,rid,1 priority,retrieval ranking FROM neural_base32),
            dedup AS (
                SELECT * FROM raw QUALIFY row_number() OVER(
                    PARTITION BY anchor,rid ORDER BY priority,ranking DESC)=1)
            SELECT d.anchor,d.rid FROM dedup d JOIN test t ON d.rid=t.rowid
            QUALIFY row_number() OVER(PARTITION BY d.anchor
                ORDER BY d.priority,d.ranking DESC,t.entity_id)<=32''')
        records=c.execute('''SELECT p.anchor,t.entity_id,l.business_name,l.business_address,
            t.business_name,t.business_address FROM neural_candidates p
            JOIN batch_anchors l ON p.anchor=l.entity_id
            JOIN test t ON p.rid=t.rowid ORDER BY p.anchor,t.entity_id''').fetchall()
        expected={anchor:[] for anchor,_,_ in anchors}
        matches={anchor:[] for anchor,_,_ in anchors}
        for anchor,target,*_ in records:
            expected[anchor].append(target)
        if max(map(len,expected.values()))>32:
            raise ValueError('Candidate cap exceeded')
        # Freeze the exact blocker output before running either pair matcher.
        write_tsv(shard/'candidate_pairs.tsv',expected,'candidate_entity_ids')
        base_probs={}
        if cat_path is not None:
            c.execute('''CREATE OR REPLACE TEMP TABLE neural_base_scored AS
                SELECT b.* FROM neural_base32 b
                JOIN neural_candidates p ON b.anchor=p.anchor AND b.rid=p.rid''')
            c.execute(pair_query('test','batch_anchors','neural_base_scored'))
            while rows:=c.fetchmany(16000):
                ids,features=score_rows(rows)
                probabilities=cat.predict_proba(features,thread_count=8)[:,1]
                base_probs.update((pair,float(p)) for pair,p in zip(ids,probabilities))
        with torch.inference_mode():
            for start in range(0,len(records),128):
                rows=records[start:start+128]
                inputs=pair_tokenizer([serialize(r[2],r[3]) for r in rows],
                                      [serialize(r[4],r[5]) for r in rows],
                                      padding=True,truncation=True,max_length=160,
                                      return_tensors='pt').to('cuda')
                with torch.autocast('cuda',dtype=torch.bfloat16):
                    logits=matcher(**inputs).logits.squeeze(-1).float().cpu().numpy()
                # Compare logits directly to avoid unnecessary sigmoid rounding.
                logit_gate=float(np.log(threshold/(1-threshold)))
                for row,logit in zip(rows,logits):
                    key=(row[0],row[1])
                    if cat_path is not None:
                        probability=base_probs.get(key)
                        if probability is None:
                            decision=float(logit)+dense_prior
                        else:
                            safe=float(np.clip(probability,1e-7,1-1e-7))
                            decision=float(logit)+float(np.log(safe/(1-safe)))
                    else:
                        decision=float(logit)
                    if decision>=logit_gate:
                        matches[row[0]].append(row[1])
        write_tsv(shard/'matching_results.tsv',matches,'matched_entity_ids')
        proof={name:sha256(shard/name) for name in ('matching_results.tsv','candidate_pairs.tsv')}
        done.write_text(json.dumps(proof),encoding='utf-8')
        if checkpoint:
            checkpoint()
        print(f'Neural {country} {partition}/{partitions}: {min(offset+batch_size,total):,}/{total:,} '
              f'anchors, {len(records):,} pairs; {time.monotonic()-started:.1f}s',flush=True)
    for filename in ('matching_results.tsv','candidate_pairs.tsv'):
        dest=out/filename
        with (out/(filename+'.tmp')).open('wb') as target:
            for i,shard in enumerate(folders):
                with (shard/filename).open('rb') as source:
                    header=source.readline()
                    if i==0:
                        target.write(header)
                    shutil.copyfileobj(source,target,1<<20)
        (out/(filename+'.tmp')).replace(dest)
    report={'country':country,'partition':partition,'partitions':partitions,
            'anchors':total,'candidate_cap':32,'dense_slots':16,'base_cap':160,
            'nprobe':64,'cross_threshold':threshold,
            'matcher':'catboost_plus_cross' if cat_path is not None else 'cross_only',
            'dense_prior':dense_prior if cat_path is not None else None,
            'matching_sha256':sha256(out/'matching_results.tsv'),
            'candidate_sha256':sha256(out/'candidate_pairs.tsv'),
            'seconds':time.monotonic()-started}
    (out/'completion.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    c.close()
    return report
