"""Evaluate the exact 32-pair dense/lexical candidate pool end to end."""
import json
import time
from pathlib import Path

import numpy as np

from .dense_training import serialize


def score_dense_only(db, pair_path, model_path, out):
    import duckdb
    import torch
    from transformers import AutoModelForSequenceClassification,AutoTokenizer

    pairs=[]
    with Path(pair_path).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['dense_only']:
                pairs.append((row['anchor'],row['target']))
    needed=sorted({i for pair in pairs for i in pair})
    c=duckdb.connect(str(db),read_only=True)
    c.execute('CREATE TEMP TABLE needed AS SELECT unnest(?) entity_id',[needed])
    records={i:serialize(n,a) for i,n,a in c.execute('''SELECT t.entity_id,t.business_name,
        t.business_address FROM train t JOIN needed x USING(entity_id)''').fetchall()}
    if len(records)!=len(needed):
        raise ValueError('Missing dense-only candidate record')
    tokenizer=AutoTokenizer.from_pretrained(model_path)
    model=AutoModelForSequenceClassification.from_pretrained(model_path).eval().cuda()
    torch.set_num_threads(4)
    scores=np.empty(len(pairs),np.float32)
    started=time.monotonic()
    with torch.inference_mode():
        for start in range(0,len(pairs),128):
            rows=pairs[start:start+128]
            inputs=tokenizer([records[a] for a,_ in rows],
                             [records[t] for _,t in rows],padding=True,truncation=True,
                             max_length=160,return_tensors='pt').to('cuda')
            with torch.autocast('cuda',dtype=torch.bfloat16):
                scores[start:start+len(rows)]=model(**inputs).logits.squeeze(-1).float().cpu().numpy()
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out,anchor=np.array([a for a,_ in pairs]),
                        target=np.array([t for _,t in pairs]),logit=scores)
    return {'pairs':len(pairs),'seconds':time.monotonic()-started,
            'country_fold':str(pair_path),'out':str(out)}


def evaluate_capped_match(baseline, retrieval_root, cross_root, dense_score_root, out,
                          scheme='capped'):
    from .experiment import choose_threshold
    from .v2 import score_slices

    baseline=Path(baseline)
    meta=json.loads((baseline/'anchors.json').read_text())
    byid={m['id']:i for i,m in enumerate(meta)}
    with np.load(baseline/'evaluation.npz') as z:
        base_g,base_t,base_p=(z[k] for k in ('groups','target','prob'))
    base_logit=np.full(len(base_g),np.nan,np.float32)
    for fold in ('calibrate','holdout'):
        for part in range(8):
            with np.load(Path(cross_root)/f'{fold}_part{part}.npz') as z:
                base_logit[z['indices']]=z['logits']
    selected={}
    for country in ('India','US'):
        for fold,prefix in [('calibrate','cal'),('holdout','hold')]:
            path=Path(retrieval_root)/country/f'{scheme}_{prefix}_pairs.jsonl'
            if not path.exists():
                raise FileNotFoundError(path)
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    row=json.loads(line)
                    selected[row['anchor'],row['target']]=row['dense_only']
    values={}
    for g,t,p,logit in zip(base_g,base_t,base_p,base_logit):
        anchor=meta[int(g)]['id'];target=str(t)
        if (anchor,target) in selected and not selected[anchor,target]:
            if not np.isfinite(logit):
                raise ValueError('Missing cross score on retained v3 candidate')
            values[anchor,target]=(float(p),float(logit))
    for country in ('India','US'):
        for prefix in ('cal','hold'):
            path=Path(dense_score_root)/f'{country}_{prefix}.npz'
            with np.load(path) as z:
                for anchor,target,logit in zip(z['anchor'],z['target'],z['logit']):
                    pair=(str(anchor),str(target))
                    if pair in values:
                        raise ValueError('Dense-only candidate duplicated baseline')
                    values[pair]=(None,float(logit))
    if len(values)!=len(selected):
        raise ValueError(f'Incomplete capped scores: {len(values)} vs {len(selected)}')
    keys=list(selected)
    groups=np.array([byid[a] for a,_ in keys],np.int32)
    targets=np.array([t for _,t in keys])
    dense=np.array([selected[k] for k in keys],bool)
    cross=np.array([values[k][1] for k in keys],np.float32)
    cat=np.array([values[k][0] if not selected[k] else .5 for k in keys],np.float32)
    oldlogit=np.log(np.clip(cat,1e-7,1-1e-7)/(1-np.clip(cat,1e-7,1-1e-7)))
    cal=[i for i,m in enumerate(meta) if m['fold']=='calibrate']
    variants=[]
    for name,beta in [('cross_only',None),('dense_prior_-2',-2.),
                      ('dense_prior_-1',-1.),('dense_prior_0',0.),
                      ('dense_prior_1',1.)]:
        logits=cross if beta is None else oldlogit+cross+np.where(dense,beta,0.)
        probability=1/(1+np.exp(-np.clip(logits,-30,30)))
        threshold,_=choose_threshold(meta,groups,targets,probability,cal)
        variants.append({'name':name,'dense_prior':beta,'threshold':threshold,
                         'calibration':score_slices(meta,groups,targets,probability,'calibrate',threshold),
                         'holdout':score_slices(meta,groups,targets,probability,'holdout',threshold)})
    best=max(variants,key=lambda r:r['calibration']['all']['macro_f0_5'])
    report={'protocol':'Exact dense top16 plus top v3 lexical/character candidates, cap32; complete train target inventory; cross-encoder scores all selected pairs; threshold chosen calibration only',
            'scheme':scheme,
            'pairs':len(keys),'dense_only_pairs':int(dense.sum()),
            'variants':variants,'selected':best}
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
