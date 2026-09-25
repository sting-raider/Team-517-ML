"""Matched-pool training with inventory-frequency and relative-rank evidence."""
import json
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from .blocking import build_index, candidates
from .data import connect
from .experiment import fold, choose_threshold, mappings
from .features import FEATURE_NAMES, batch_features
from .metrics import evaluate

V2_NAMES = FEATURE_NAMES + ['log_anchor_name_frequency', 'log_anchor_address_frequency',
    'log_target_name_frequency', 'log_target_address_frequency',
    'log_candidate_rank', 'relative_retrieval_score']


def frequency_tables(c, split):
    for side, condition in (('left', 'source=1'), ('right', 'source>1')):
        for field in ('n', 'a'):
            c.execute(f'''CREATE OR REPLACE TABLE v2_{side}_{field} AS
                SELECT country,{field},count(*)::INTEGER AS freq FROM {split}
                WHERE {condition} AND {field}<>'' GROUP BY country,{field}''')


def pair_query(split, anchors, pairs):
    return f'''WITH ranked AS (
        SELECT p.*,row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC,r.entity_id) AS ranking,
               max(retrieval) OVER(PARTITION BY anchor) AS top_retrieval
        FROM {pairs} p JOIN {split} r ON p.rid=r.rowid)
        SELECT p.anchor,r.entity_id,l.n,l.a,r.n,r.a,p.retrieval,p.hits,r.source,
          ln(1+coalesce(lnf.freq,0)),ln(1+coalesce(laf.freq,0)),
          ln(1+coalesce(rnf.freq,0)),ln(1+coalesce(raf.freq,0)),
          ln(1+p.ranking),p.retrieval/greatest(1,p.top_retrieval)
        FROM ranked p JOIN {anchors} l ON p.anchor=l.entity_id
        JOIN {split} r ON p.rid=r.rowid
        LEFT JOIN v2_left_n lnf ON l.country=lnf.country AND l.n=lnf.n
        LEFT JOIN v2_left_a laf ON l.country=laf.country AND l.a=laf.a
        LEFT JOIN v2_right_n rnf ON r.country=rnf.country AND r.n=rnf.n
        LEFT JOIN v2_right_a raf ON r.country=raf.country AND r.a=raf.a
        ORDER BY p.anchor,r.entity_id'''


def compute_rows(rows):
    base = batch_features([row[2:9] for row in rows])
    extra = np.asarray([row[9:] for row in rows], dtype=np.float32)
    return [(r[0],r[1]) for r in rows], np.concatenate((base,extra),axis=1)


def feature_batches(c, query, executor):
    c.execute(query)
    pending = deque()
    while rows := c.fetchmany(16000):
        if len(pending) >= 8:
            yield pending.popleft().result()
        pending.append(executor.submit(compute_rows, rows))
    while pending:
        yield pending.popleft().result()


def select_anchors(c, partition, partitions, training_end=200000, confirmation=False):
    # The 30k development population is preserved. 30k:50k never enters fitting.
    c.execute('''CREATE OR REPLACE TEMP TABLE ordered_s1 AS SELECT *,
        row_number() OVER(ORDER BY md5('sample517:'||entity_id)) AS sample_position
        FROM train WHERE source=1''')
    if confirmation:
        condition = 'sample_position>40000 AND sample_position<=45000'
    else:
        condition = f'(sample_position<=30000 OR (sample_position>50000 AND sample_position<={int(training_end)}))'
    rows = c.execute(f'''SELECT entity_id,sample_position FROM ordered_s1
        WHERE {condition} AND hash(entity_id)%{int(partitions)}={int(partition)}''').fetchall()
    selected = [(i, 'confirmation' if confirmation else fold(i)) for i,pos in rows
                if confirmation or pos<=30000 or fold(i)=='fit']
    c.execute('CREATE OR REPLACE TEMP TABLE selected_ids(entity_id VARCHAR, fold VARCHAR)')
    c.executemany('INSERT INTO selected_ids VALUES (?,?)', selected)
    c.execute('''CREATE OR REPLACE TEMP TABLE v2_anchors AS
        SELECT a.*,s.fold,row_number() OVER(ORDER BY a.entity_id) AS seq
        FROM ordered_s1 a JOIN selected_ids s USING(entity_id)''')
    return [{'id':i,'country':co,'fold':f,'truth':matches.split(',') if matches else []}
        for i,co,f,matches in c.execute('''SELECT a.entity_id,a.country,a.fold,t.matches
          FROM v2_anchors a JOIN truth t ON a.entity_id=t.anchor ORDER BY a.entity_id''').fetchall()]


def materialize(db, out, partition=0, partitions=8, training_end=200000, cap=160, confirmation=False):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    if (out/'ready.json').exists():
        raise ValueError('Use a fresh feature directory; no silent cache reuse')
    c=connect(db); c.execute("SET memory_limit='12GB'"); c.execute('SET threads=8')
    build_index(c,'train'); frequency_tables(c,'train')
    meta=select_anchors(c,partition,partitions,training_end,confirmation)
    lookup={m['id']:i for i,m in enumerate(meta)}
    truths=[set(m['truth']) for m in meta]
    width=c.execute('SELECT max(length(entity_id)) FROM train').fetchone()[0]
    chunks=[]; started=time.time()
    with ProcessPoolExecutor(max_workers=8) as executor:
        for offset in range(0,len(meta),5000):
            c.execute(f'''CREATE OR REPLACE TEMP TABLE batch_anchors AS SELECT * FROM v2_anchors
                WHERE seq>{offset} AND seq<={offset+5000}''')
            candidates(c,'train','batch_anchors','batch_candidates',cap)
            count=c.execute('SELECT count(*) FROM batch_candidates').fetchone()[0]
            x=np.empty((count,len(V2_NAMES)),np.float32); y=np.empty(count,np.uint8)
            groups=np.empty(count,np.int32); targets=np.empty(count,dtype=f'U{width}')
            pos=0
            for ids,values in feature_batches(c,pair_query('train','batch_anchors','batch_candidates'),executor):
                end=pos+len(ids); x[pos:end]=values
                for j,(anchor,target) in enumerate(ids,pos):
                    g=lookup[anchor]; groups[j]=g; targets[j]=target; y[j]=target in truths[g]
                pos=end
            path=out/f'chunk_{offset:07d}.npz'
            np.savez(path,x=x,y=y,groups=groups,target=targets)
            chunks.append(path.name)
            print(f'Features part {partition}: {min(offset+5000,len(meta))}/{len(meta)} anchors; {time.time()-started:.1f}s',flush=True)
    (out/'anchors.json').write_text(json.dumps(meta),encoding='utf-8')
    receipt={'partition':partition,'partitions':partitions,'training_end':training_end,
        'candidate_cap':cap,'feature_names':V2_NAMES,'anchors':len(meta),'chunks':chunks,
        'confirmation':confirmation,'elapsed_seconds':time.time()-started}
    (out/'ready.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    c.close(); return receipt


def load_parts(root, partitions):
    arrays=[]; meta=[]
    for part in range(partitions):
        folder=Path(root)/f'part{part}'
        receipt=json.loads((folder/'ready.json').read_text())
        if receipt['feature_names']!=V2_NAMES:
            raise ValueError('Feature schema mismatch')
        part_meta=json.loads((folder/'anchors.json').read_text())
        for name in receipt['chunks']:
            with np.load(folder/name) as data:
                arrays.append((data['x'],data['y'],data['groups']+len(meta),data['target']))
        meta.extend(part_meta)
    if len({m['id'] for m in meta})!=len(meta):
        raise ValueError('Partition overlap')
    return (*[np.concatenate([row[i] for row in arrays]) for i in range(4)],meta)


def score_slices(meta,groups,target,prob,fold_name,threshold):
    result={}
    for country in [None]+sorted({m['country'] for m in meta}):
        indices=[i for i,m in enumerate(meta) if m['fold']==fold_name and (country is None or m['country']==country)]
        if indices:
            truth,pred,cand=mappings(meta,groups,target,prob,indices,threshold)
            result[country or 'all']=evaluate(truth,pred,cand)
    return result


def train(root,out,baseline,partitions=8,depth=8):
    from catboost import CatBoostClassifier
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    x,y,groups,target,meta=load_parts(root,partitions)
    fit_ids=[i for i,m in enumerate(meta) if m['fold']=='fit']
    early_ids=[i for i,m in enumerate(meta) if m['fold']=='early']
    cal_ids=[i for i,m in enumerate(meta) if m['fold']=='calibrate']
    fit=np.isin(groups,fit_ids);early=np.isin(groups,early_ids);ev=~fit
    counts=np.bincount(groups,minlength=len(meta))
    weights=1/np.maximum(1,counts[groups[fit]]); weights/=weights.mean()
    print(f'Training depth {depth}: {len(fit_ids)} anchors; {int(fit.sum()):,} fit pairs; {int(y[fit].sum()):,} positives',flush=True)
    model=CatBoostClassifier(iterations=1800,depth=depth,learning_rate=.05,loss_function='Logloss',
        l2_leaf_reg=10,random_seed=517,task_type='GPU',devices='0',thread_count=8,
        verbose=100,allow_writing_files=False)
    started=time.time()
    model.fit(x[fit],y[fit],sample_weight=weights,eval_set=(x[early],y[early]),early_stopping_rounds=120)
    model.save_model(str(out/'mixed.cbm'))
    eg,et=groups[ev],target[ev]
    p=model.predict_proba(x[ev],thread_count=8)[:,1]
    threshold,curve=choose_threshold(meta,eg,et,p,cal_ids)
    old=CatBoostClassifier();old.load_model(str(Path(baseline)/'mixed.cbm'))
    bp=old.predict_proba(x[ev,:len(FEATURE_NAMES)],thread_count=8)[:,1]
    report={'training_anchors':len(fit_ids),'training_pairs':int(fit.sum()),'depth':depth,
        'trees':model.tree_count_,'threshold':threshold,'candidate_cap':160,
        'training_seconds':time.time()-started,'features':V2_NAMES,'calibration_curve':curve,
        'baseline':{f:score_slices(meta,eg,et,bp,f,.5750000000000002) for f in ('calibrate','holdout')},
        'new':{f:score_slices(meta,eg,et,p,f,threshold) for f in ('calibrate','holdout')}}
    config={'feature_names':V2_NAMES,'feature_version':2,'threshold':threshold,'candidate_cap':160,
        'shortlist_cap':160,'seed':517,'depth':depth,'blocker':'v2','training_anchors':len(fit_ids)}
    (out/'model_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    (out/'anchors.json').write_text(json.dumps(meta),encoding='utf-8')
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    np.savez(out/'evaluation.npz',groups=eg,target=et,prob=p,baseline=bp,y=y[ev])
    print(json.dumps({k:report[k] for k in ('training_anchors','training_pairs','trees','threshold','baseline','new')},indent=2),flush=True)
    return report
