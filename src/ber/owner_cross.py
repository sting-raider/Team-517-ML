"""Compare bounded competing Source-1 owners using the licensed M017 pair model."""
import json
import time
from pathlib import Path

import numpy as np

from .dense_training import serialize


def score_fold(owner_root, cross_path, out, topk=3):
    import duckdb
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    started=time.monotonic()
    owner_root=Path(owner_root)
    with np.load(owner_root/'pair_scores.npz') as z:
        targets=z['target'].astype(str)
        owners=z['owner'].astype(str)
        similarities=z['dense'].astype(np.float32)
    if len(targets)!=len(owners) or len(targets)!=len(similarities):
        raise ValueError('Owner score arrays have inconsistent lengths')
    order=np.lexsort((-similarities,targets))
    selected=set()
    previous=None
    rank=0
    for i in order:
        target=targets[i]
        if target!=previous:
            previous=target
            rank=0
        if rank<topk:
            selected.add((target,owners[i]))
        rank+=1
    evidence=json.loads((owner_root/'evaluation.json').read_text(encoding='utf-8'))
    predicted={(target,owner) for target,owner,_ in evidence['predictions']}
    selected.update(predicted)
    rows=sorted(selected)
    c=duckdb.connect()
    raw=c.execute('SELECT * FROM read_parquet(?)',
                  [str(owner_root/'records.parquet')]).fetchall()
    records={identifier:serialize(name,address) for identifier,name,address in raw}
    missing={i for pair in rows for i in pair if i not in records}
    if missing:
        raise ValueError(f'{len(missing)} owner records missing')
    torch.set_num_threads(4)
    tokenizer=AutoTokenizer.from_pretrained(cross_path)
    model=AutoModelForSequenceClassification.from_pretrained(cross_path).eval().cuda()
    logits=np.empty(len(rows),np.float32)
    with torch.inference_mode():
        for start in range(0,len(rows),128):
            batch=rows[start:start+128]
            inputs=tokenizer([records[owner] for _,owner in batch],
                             [records[target] for target,_ in batch],
                             padding=True,truncation=True,max_length=160,
                             return_tensors='pt').to('cuda')
            with torch.autocast('cuda',dtype=torch.bfloat16):
                logits[start:start+len(batch)]=model(**inputs).logits.squeeze(-1).float().cpu().numpy()
            if start and start%16384==0:
                print(f'Owner cross: {start:,}/{len(rows):,} pairs',flush=True)
    out=Path(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out,target=np.array([t for t,_ in rows]),
                        owner=np.array([o for _,o in rows]),logit=logits)
    report={'fold':owner_root.name,'topk':topk,'pairs':len(rows),
            'predicted_owners_included':len(predicted),
            'seconds':time.monotonic()-started,
            'protocol':'Top three frozen E5 reverse owners per target plus all original predicted owners; M017 cross-encoder sees only supplied record text'}
    out.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def evaluate_folds(d017_root,score_root,out):
    from .metrics import evaluate

    data={}
    for fold in ('calibrate','holdout'):
        evidence=json.loads((Path(d017_root)/fold/'evaluation.json').read_text())
        truth={m['id']:set(m['truth']) for m in evidence['meta']}
        country={m['id']:m['country'] for m in evidence['meta']}
        originals=evidence['predictions']
        with np.load(Path(score_root)/f'{fold}.npz') as z:
            score={(str(t),str(o)):float(p) for t,o,p in
                   zip(z['target'],z['owner'],z['logit'])}
        best={}
        for (target,_),value in score.items():
            best[target]=max(best.get(target,-float('inf')),value)
        baseline={}
        for target,owner,_ in originals:
            baseline.setdefault(owner,set()).add(target)
        variants={}
        for margin in (0.,.5,1.,2.,3.,4.,6.):
            pred={}
            removed_tp=removed_fp=missing=0
            for target,owner,_ in originals:
                key=(target,owner)
                if key not in score:
                    missing+=1
                    pred.setdefault(owner,set()).add(target)
                elif best[target]>score[key]+margin+1e-7:
                    removed_tp+=target in truth[owner]
                    removed_fp+=target not in truth[owner]
                else:
                    pred.setdefault(owner,set()).add(target)
            variants[str(margin)]={'macro_f0_5':evaluate(truth,pred)['macro_f0_5'],
                'India':evaluate({k:v for k,v in truth.items() if country[k]=='India'},pred)['macro_f0_5'],
                'US':evaluate({k:v for k,v in truth.items() if country[k]=='US'},pred)['macro_f0_5'],
                'removed_true':removed_tp,'removed_false':removed_fp,
                'original_unscored':missing}
        data[fold]={'baseline':evaluate(truth,baseline)['macro_f0_5'],
                    'variants':variants}
    selected=max(data['calibrate']['variants'],
                 key=lambda margin:data['calibrate']['variants'][margin]['macro_f0_5'])
    report={'protocol':'Original v3 predictions only; top3 E5 reverse owners plus original owner, ranked by frozen M017 cross-encoder; margin selected on calibration and checked on holdout',
            'folds':data,'selected_margin':selected}
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
