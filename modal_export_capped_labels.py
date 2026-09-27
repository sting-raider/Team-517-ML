"""Export labeled capped-pair decisions for local error analysis."""

import json
from pathlib import Path

import modal
from modal_app import VOLUME_ROOT, volume


image = (modal.Image.debian_slim(python_version='3.12')
         .pip_install('numpy==2.3.2')
         .add_local_python_source('modal_app'))
app = modal.App('team517-export-capped-labels')


@app.function(image=image, volumes={str(VOLUME_ROOT): volume},
              cpu=2, memory=8192, timeout=900)
def export():
    import numpy as np

    base = VOLUME_ROOT / 'project/experiments/int003/depth10'
    retrieve = VOLUME_ROOT / 'project/experiments/int005_retrieval'
    m017 = VOLUME_ROOT / 'project/experiments/m017/scores'
    capped = VOLUME_ROOT / 'project/experiments/capped_match'
    m021 = VOLUME_ROOT / 'project/experiments/m021/capped_scores'
    meta = json.loads((base / 'anchors.json').read_text())
    byid = {m['id']: i for i,m in enumerate(meta)}
    with np.load(base / 'evaluation.npz') as z:
        groups,targets,probs = (z[k] for k in ('groups','target','prob'))
    logits = np.full(len(groups), np.nan, np.float32)
    for fold in ('calibrate','holdout'):
        for part in range(8):
            with np.load(m017 / f'{fold}_part{part}.npz') as z:
                logits[z['indices']] = z['logits']
    selected = {}
    for country in ('India','US'):
        for fold,prefix in [('calibrate','cal'),('holdout','hold')]:
            with (retrieve / country / f'capped_{prefix}_pairs.jsonl').open() as stream:
                for line in stream:
                    row = json.loads(line)
                    selected[row['anchor'],row['target']] = row['dense_only']
    values = {}
    for g,t,p,logit in zip(groups,targets,probs,logits):
        key = meta[int(g)]['id'],str(t)
        if key in selected and not selected[key]:
            values[key] = float(p),float(logit)
    for country in ('India','US'):
        for prefix in ('cal','hold'):
            with np.load(capped / f'{country}_{prefix}.npz') as z:
                for a,t,logit in zip(z['anchor'],z['target'],z['logit']):
                    values[str(a),str(t)] = .5,float(logit)
    if set(values) != set(selected):
        raise ValueError(f'Coverage {len(values)} vs {len(selected)}')
    larger={}
    for country in ('India','US'):
        for prefix in ('cal','hold'):
            with np.load(m021 / f'{country}_{prefix}.npz') as z:
                for a,t,logit in zip(z['anchor'],z['target'],z['logit']):
                    larger[str(a),str(t)]=float(logit)
    if set(larger)!=set(selected):
        raise ValueError(f'M021 coverage {len(larger)} vs {len(selected)}')
    keys = list(selected)
    dense = np.array([selected[k] for k in keys], dtype=bool)
    cross = np.array([values[k][1] for k in keys], dtype=np.float32)
    m021_cross = np.array([larger[k] for k in keys], dtype=np.float32)
    cat = np.array([values[k][0] for k in keys], dtype=np.float32)
    oldlogit = np.log(np.clip(cat,1e-7,1-1e-7)/(1-np.clip(cat,1e-7,1-1e-7)))
    fused = cross + oldlogit + np.where(dense,-2.,0.)
    chosen = fused >= np.log(.95/.05)
    truth = np.array([t in meta[byid[a]]['truth'] for a,t in keys], dtype=bool)
    out = VOLUME_ROOT / 'project/experiments/capped_match/local_decisions.npz'
    np.savez_compressed(out, anchor=np.array([a for a,_ in keys]),
                        target=np.array([t for _,t in keys]),
                        fold=np.array([meta[byid[a]]['fold'] for a,_ in keys]),
                        country=np.array([meta[byid[a]]['country'] for a,_ in keys]),
                        dense=dense,cross=cross,cat=cat,fused=fused,
                        m021_cross=m021_cross,chosen=chosen,truth=truth)
    volume.commit()
    return {'pairs':len(keys),'truth':int(truth.sum()),
            'predicted':int(chosen.sum()),'size':out.stat().st_size}


@app.local_entrypoint()
def main():
    print(json.dumps(export.remote()))
