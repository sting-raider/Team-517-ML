"""M017 multilingual pair reranker, fit only on supplied training labels."""
import json
import math
import random
import time
from pathlib import Path

import numpy as np
from .dense_training import serialize

MODEL = 'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1'
REVISION = '1427fd652930e4ba29e8149678df786c240d8825'


def train(data_root, out, max_seconds=3000, callback=None,
          positive_limit=2):
    import torch
    import torch.nn.functional as F
    from huggingface_hub import HfApi
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    random.seed(517);np.random.seed(517);torch.manual_seed(517)
    torch.set_num_threads(4)
    info = HfApi().model_info(MODEL, revision=REVISION)
    license_name = info.card_data.get('license')
    if license_name != 'apache-2.0':
        raise ValueError('Pinned cross-encoder checkpoint license mismatch')
    if info.sha != REVISION:
        raise ValueError('Pinned cross-encoder checkpoint revision mismatch')
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL,revision=REVISION).cuda()
    if model.config.num_labels != 1:
        raise ValueError('Expected pretrained scalar ranking head')
    parameters = sum(p.numel() for p in model.parameters())
    if parameters > 8_000_000_000:
        raise ValueError('Competition parameter cap exceeded')
    rng = random.Random(517)
    pairs = []
    anchors = 0
    for path in sorted(Path(data_root).glob('part*.jsonl')):
        with path.open(encoding='utf-8') as src:
            for line in src:
                row = json.loads(line)
                positives = row['positives']
                if not positives or not row['negatives']:
                    continue
                anchors += 1
                selected=positives if positive_limit is None else \
                    rng.sample(positives,min(positive_limit,len(positives)))
                for _,text in selected:
                    pairs.append((row['query'],text,1.))
                for _,text in row['negatives']:
                    pairs.append((row['query'],text,0.))
    if anchors < 90000:
        raise ValueError('Missing fit anchors for pair training')
    rng.shuffle(pairs)
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    optimizer=torch.optim.AdamW(model.parameters(),lr=2e-5,weight_decay=.01)
    batch_size=32
    total_steps=math.ceil(len(pairs)/batch_size)
    losses=[];step=0
    started=time.monotonic()
    model.train()
    for start in range(0,len(pairs),batch_size):
        batch=pairs[start:start+batch_size]
        encoded=tokenizer([r[0] for r in batch],[r[1] for r in batch],
                          padding=True,truncation=True,max_length=160,
                          return_tensors='pt').to('cuda')
        labels=torch.tensor([r[2] for r in batch],device='cuda')
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.bfloat16):
            logits=model(**encoded).logits.squeeze(-1).float()
            loss=F.binary_cross_entropy_with_logits(logits,labels)
        if not torch.isfinite(loss):
            raise ValueError('Nonfinite cross-encoder loss')
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
        warmup=min(1.,(step+1)/250)
        decay=max(.1,1-step/max(1,total_steps))
        for group in optimizer.param_groups:
            group['lr']=2e-5*warmup*decay
        optimizer.step()
        step+=1
        losses.append(float(loss.detach()))
        if step%100==0:
            print(f'M017 step {step}/{total_steps}: loss {np.mean(losses[-100:]):.4f}; '
                  f'{time.monotonic()-started:.1f}s',flush=True)
        if step%2000==0:
            model.save_pretrained(out)
            tokenizer.save_pretrained(out)
            if callback:
                callback()
        if time.monotonic()-started>=max_seconds:
            break
    model.save_pretrained(out)
    tokenizer.save_pretrained(out)
    report={'initialization':MODEL,'revision':REVISION,'license':license_name,
            'parameters':parameters,'fit_anchors':anchors,'training_pairs':len(pairs),
            'positives':sum(r[2] for r in pairs),'steps':step,'planned_steps':total_steps,
            'seconds':time.monotonic()-started,'stopped_on_time_budget':step<total_steps,
            'batch_size':batch_size,'max_length':160,'seed':517,
            'positive_limit_per_anchor':positive_limit,
            'initial_loss_100':float(np.mean(losses[:100])),
            'final_loss_100':float(np.mean(losses[-100:])),
            'peak_gpu_bytes':torch.cuda.max_memory_allocated(),
            'note':'Training loss only; no held-out entity F0.5 established.'}
    (out/'training_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def score_partition(db, baseline, model_path, out, fold, part, parts=8):
    """Score every v3 candidate for one complete group partition of a holdout fold."""
    import duckdb
    import torch
    from transformers import AutoModelForSequenceClassification,AutoTokenizer

    baseline=Path(baseline)
    meta=json.loads((baseline/'anchors.json').read_text())
    with np.load(baseline/'evaluation.npz') as z:
        groups=z['groups'];targets=z['target']
    wanted=np.array([i for i,m in enumerate(meta) if m['fold']==fold],dtype=np.int32)
    indices=np.flatnonzero(np.isin(groups,wanted)&(groups%parts==part))
    if len(indices)<20000:
        raise ValueError('Cross-encoder scoring shard unexpectedly small')
    anchors=[meta[int(groups[i])]['id'] for i in indices]
    candidates=[str(targets[i]) for i in indices]
    needed=sorted(set(anchors)|set(candidates))
    c=duckdb.connect(str(db),read_only=True)
    c.execute('CREATE TEMP TABLE needed AS SELECT unnest(?) entity_id',[needed])
    records={i:serialize(n,a) for i,n,a in c.execute('''
        SELECT t.entity_id,t.business_name,t.business_address FROM train t
        JOIN needed x USING(entity_id)''').fetchall()}
    if len(records)!=len(needed):
        raise ValueError('Missing pair record')
    tokenizer=AutoTokenizer.from_pretrained(model_path)
    model=AutoModelForSequenceClassification.from_pretrained(model_path).eval().cuda()
    torch.set_num_threads(4)
    scores=np.empty(len(indices),np.float32)
    started=time.monotonic()
    with torch.inference_mode():
        for start in range(0,len(indices),128):
            aa=anchors[start:start+128];tt=candidates[start:start+128]
            inp=tokenizer([records[i] for i in aa],[records[i] for i in tt],
                          padding=True,truncation=True,max_length=160,
                          return_tensors='pt').to('cuda')
            with torch.autocast('cuda',dtype=torch.bfloat16):
                scores[start:start+len(aa)]=model(**inp).logits.squeeze(-1).float().cpu().numpy()
            if start%(128*100)==0:
                print(f'M017 {fold} part{part}: {start+len(aa)}/{len(indices)} in '
                      f'{time.monotonic()-started:.1f}s',flush=True)
    out=Path(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out,indices=indices,logits=scores)
    c.close()
    return {'fold':fold,'part':part,'parts':parts,'pairs':len(indices),
            'seconds':time.monotonic()-started,'output':str(out)}


def evaluate_pair_model(baseline,parts_root,out):
    from .experiment import choose_threshold
    from .v2 import score_slices

    baseline=Path(baseline)
    meta=json.loads((baseline/'anchors.json').read_text())
    with np.load(baseline/'evaluation.npz') as z:
        groups,target,p=(z[k] for k in ('groups','target','prob'))
    logits=np.full(len(groups),np.nan,np.float32)
    for fold in ('calibrate','holdout'):
        for part in range(8):
            with np.load(Path(parts_root)/f'{fold}_part{part}.npz') as z:
                idx=z['indices'];values=z['logits']
            if np.isfinite(logits[idx]).any():
                raise ValueError('Scoring partitions overlap')
            logits[idx]=values
    chosen=np.array([m['fold'] in ('calibrate','holdout') for m in meta])
    if not np.isfinite(logits[np.isin(groups,np.flatnonzero(chosen))]).all():
        raise ValueError('Incomplete scored calibration or holdout pool')
    cal=[i for i,m in enumerate(meta) if m['fold']=='calibrate']
    hold=[i for i,m in enumerate(meta) if m['fold']=='holdout']
    baseline_result={fold:score_slices(meta,groups,target,p,fold,.625)
                     for fold in ('calibrate','holdout')}
    safe_p=np.clip(p,1e-7,1-1e-7)
    old_logit=np.log(safe_p/(1-safe_p))
    candidates=[]
    for name,alpha in [('cross_only',None),('ensemble_0.1',.1),
                       ('ensemble_0.25',.25),('ensemble_0.5',.5),
                       ('ensemble_1',1.),('ensemble_2',2.)]:
        new_logit=np.nan_to_num(logits,nan=0.) if alpha is None else \
                  old_logit+alpha*np.nan_to_num(logits,nan=0.)
        transformed=1/(1+np.exp(-np.clip(new_logit,-30,30)))
        threshold,_=choose_threshold(meta,groups,target,transformed,cal)
        cal_score=score_slices(meta,groups,target,transformed,'calibrate',threshold)
        hold_score=score_slices(meta,groups,target,transformed,'holdout',threshold)
        candidates.append({'name':name,'alpha':alpha,'threshold':threshold,
                           'calibration':cal_score,'holdout':hold_score})
    best=max(candidates,key=lambda x:x['calibration']['all']['macro_f0_5'])
    report={'protocol':'Full v3 candidate pool on the existing calibration and development holdout anchors; threshold/ensemble chosen on calibration only',
            'baseline':baseline_result,'variants':candidates,'selected':best,
            'scored_pairs':int(np.isfinite(logits).sum())}
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
