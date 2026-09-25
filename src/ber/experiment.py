"""Entity-disjoint fit, early stopping, calibration, and untouched local evaluation."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from catboost import CatBoostClassifier
from .data import connect
from .features import features, FEATURE_NAMES
from .provenance import PROVENANCE_FEATURE_NAMES, provenance_values
from .metrics import evaluate


def fold(entity_id):
    bucket=int(hashlib.sha256(('fold517:'+entity_id).encode()).hexdigest()[:8],16)%100
    return 'fit' if bucket<60 else 'early' if bucket<75 else 'calibrate' if bucket<90 else 'holdout'


def materialize(db,out,anchor_table='anchors',candidate_table='candidates',provenance=False):
    c=connect(db)
    anchors=c.execute(f'SELECT a.entity_id,a.country,t.matches FROM {anchor_table} a JOIN truth t ON a.entity_id=t.anchor ORDER BY a.entity_id').fetchall()
    meta=[{'id':i,'country':country,'truth':matches.split(',') if matches else [],'fold':fold(i)} for i,country,matches in anchors]
    lookup={m['id']:i for i,m in enumerate(meta)}
    count=c.execute(f'SELECT count(*) FROM {candidate_table}').fetchone()[0]
    width=c.execute('SELECT max(length(entity_id)) FROM train').fetchone()[0]
    feature_names=FEATURE_NAMES + (PROVENANCE_FEATURE_NAMES if provenance else [])
    x=np.empty((count,len(feature_names)),dtype=np.float32)
    y=np.empty(count,dtype=np.uint8)
    groups=np.empty(count,dtype=np.int32)
    target=np.empty(count,dtype=f'U{width}')
    extra = '' if not provenance else ''',p.candidate_rank,p.name_exact_hits,p.address_exact_hits,
        p.name_token_hits,p.address_token_hits,p.address_bigram_hits,p.name_number_hits,
        p.address_number_hits,p.min_key_freq'''
    c.execute(f'''SELECT p.anchor,r.entity_id,l.n,l.a,r.n,r.a,p.retrieval,p.hits,r.source{extra}
        FROM {candidate_table} p JOIN {anchor_table} l ON p.anchor=l.entity_id JOIN train r ON p.rid=r.rowid ORDER BY p.anchor,p.rid''')
    start=time.time()
    pos=0
    while records:=c.fetchmany(20000):
        for anchor,rid,*fields in records:
            g=lookup[anchor]
            base=features(*fields[:7])
            x[pos]=base if not provenance else base+provenance_values(*fields[7:])
            y[pos]=rid in meta[g]['truth']
            groups[pos]=g
            target[pos]=rid
            pos+=1
        if pos%200000==0:
            print(f'Features {pos:,}/{count:,}, {time.time()-start:.1f}s',flush=True)
    out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out/'features.npz',x=x,y=y,groups=groups,target=target)
    (out/'feature_names.json').write_text(json.dumps(feature_names),encoding='utf-8')
    (out/'anchors.json').write_text(json.dumps(meta),encoding='utf-8')
    c.close()
    return x,y,groups,target,meta


def mappings(meta,groups,target,prob,indices,threshold):
    wanted=set(indices)
    truth={meta[i]['id']:set(meta[i]['truth']) for i in indices}
    pred={k:set() for k in truth}
    cand={k:set() for k in truth}
    for g,t,p in zip(groups,target,prob):
        if g in wanted:
            k=meta[g]['id']
            cand[k].add(str(t))
            if p>=threshold:
                pred[k].add(str(t))
    return truth,pred,cand


def choose_threshold(meta,groups,target,prob,indices):
    # Vectorized entity-level scorer. Candidate misses remain in the denominators.
    ids=np.asarray(indices,dtype=int)
    mask=np.isin(groups,ids)
    gs=groups[mask]
    ps=prob[mask]
    labs=np.array([t in meta[g]['truth'] for g,t in zip(gs,target[mask])],dtype=bool)
    sizes=np.array([len(m['truth']) for m in meta],dtype=float)
    grid=np.unique(np.r_[np.arange(.05,.96,.025),.97,.98,.99,.995,.999])
    scores=[]
    for threshold in grid:
        chosen=ps>=threshold
        n=np.bincount(gs[chosen],minlength=len(meta))
        tp=np.bincount(gs[chosen&labs],minlength=len(meta))
        den=.25*sizes+n
        s=np.divide(1.25*tp,den,out=np.zeros(len(meta)),where=den>0)
        s[(sizes==0)&(n==0)]=1
        scores.append(float(s[ids].mean()))
    best=max(range(len(grid)),key=lambda i:(scores[i],grid[i]))
    return float(grid[best]), [{'threshold':float(t),'macro_f0_5':s} for t,s in zip(grid,scores)]


def run(db,out,reports,refresh=False,transfer=False,provenance=False):
    start=time.time()
    feature_names=FEATURE_NAMES + (PROVENANCE_FEATURE_NAMES if provenance else [])
    if (out/'features.npz').exists() and not refresh:
        f=np.load(out/'features.npz')
        x,y,groups,target=(f[k] for k in ('x','y','groups','target'))
        meta=json.loads((out/'anchors.json').read_text())
        schema=out/'feature_names.json'
        if schema.exists() and json.loads(schema.read_text())!=feature_names:
            raise ValueError('Cached feature schema does not match requested provenance mode')
        if provenance and not schema.exists():
            raise ValueError('Legacy feature cache has no provenance schema; rerun with --refresh')
    else:
        x,y,groups,target,meta=materialize(db,out,provenance=provenance)
    countries=sorted({m['country'] for m in meta})
    runs=[('mixed',None)]+[(f'train_{country}',country) for country in countries] if transfer else [('mixed',None)]
    result={'anchor_count':len(meta),'candidate_pairs':len(y),'positive_candidate_pairs':int(y.sum()),
            'features':feature_names,'protocol':'60% fit, 15% early stopping, 15% threshold calibration, 10% holdout; SHA256 of anchor ID; full training S2/S3 inventory', 'runs':{}}
    for name,country in runs:
        selected=lambda f:[i for i,m in enumerate(meta) if m['fold']==f and (country is None or m['country']==country)]
        fit=np.isin(groups,selected('fit'))
        early=np.isin(groups,selected('early'))
        model=CatBoostClassifier(iterations=500,depth=7,learning_rate=.08,loss_function='Logloss',
            random_seed=517,thread_count=6,verbose=100,allow_writing_files=False,l2_leaf_reg=5)
        counts=np.bincount(groups,minlength=len(meta))
        weights=1/np.maximum(1,counts[groups[fit]])
        weights=weights/weights.mean()
        model.fit(x[fit],y[fit],sample_weight=weights,eval_set=(x[early],y[early]),early_stopping_rounds=50)
        prob=model.predict_proba(x,thread_count=6)[:,1]
        threshold,curve=choose_threshold(meta,groups,target,prob,selected('calibrate'))
        model.save_model(str(out/f'{name}.cbm'))
        np.save(out/f'{name}_probabilities.npy',prob)
        run={'threshold':threshold,'trees':model.tree_count_,'calibration_curve':curve,'holdout':{},
             'feature_importance':dict(sorted(zip(FEATURE_NAMES,map(float,model.feature_importances_)),key=lambda kv:-kv[1]))}
        for evaluation_country in [None]+countries:
            indices=[i for i,m in enumerate(meta) if m['fold']=='holdout' and (evaluation_country is None or m['country']==evaluation_country)]
            truth,pred,cand=mappings(meta,groups,target,prob,indices,threshold)
            run['holdout'][evaluation_country or 'all']=evaluate(truth,pred,cand)
        result['runs'][name]=run
        print(name,json.dumps(run['holdout']),flush=True)
        if name=='mixed':
            (out/'model_config.json').write_text(json.dumps({'threshold':threshold,'feature_names':feature_names,'candidate_cap':80,'seed':517,'provenance':provenance},indent=2))
            indices=[i for i,m in enumerate(meta) if m['fold']=='holdout']
            truth,pred,cand=mappings(meta,groups,target,prob,indices,threshold)
            errors=[{'anchor':k,'missing_candidates':sorted(truth[k]-cand[k]),'false_negatives':sorted(truth[k]-pred[k]),'false_positives':sorted(pred[k]-truth[k])} for k in truth if pred[k]!=truth[k]]
            (out/'holdout_errors.json').write_text(json.dumps(errors,indent=2))
    result['elapsed_seconds']=time.time()-start
    reports.parent.mkdir(parents=True,exist_ok=True)
    reports.write_text(json.dumps(result,indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=Path('artifacts/data.duckdb'))
    p.add_argument('--out',type=Path,default=Path('artifacts/baseline'))
    p.add_argument('--report',type=Path,default=Path('reports/baseline.json'))
    p.add_argument('--refresh',action='store_true')
    p.add_argument('--transfer',action='store_true')
    p.add_argument('--provenance',action='store_true',help='Consume M002 provenance columns from the candidate table')
    a=p.parse_args()
    run(a.db,a.out,a.report,a.refresh,a.transfer,a.provenance)


if __name__=='__main__':
    main()
