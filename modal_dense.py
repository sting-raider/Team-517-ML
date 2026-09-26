"""INT005: bounded Modal training for learned multilingual retrieval."""
import json
import shutil
from pathlib import Path

import modal
from modal_app import image, volume, VOLUME_ROOT, SCRATCH

base_image = image.add_local_python_source('modal_app')
gpu_image = (modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent / 'requirements.txt'))
    .pip_install('torch==2.8.0', 'transformers==4.57.1',
                 'huggingface_hub==0.36.0', 'sentencepiece==0.2.1', 'faiss-cpu==1.12.0')
    .env({'PYTHONPATH': '/app/src'})
    .add_local_dir(str(Path(__file__).parent / 'src'), '/app/src')
    .add_local_python_source('modal_app'))
app = modal.App('team517-int005-dense')
ROOT = VOLUME_ROOT / 'project/experiments/int005'


@app.function(image=base_image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, timeout=1800)
def prepare(partition: int):
    from ber.dense_training import prepare_partition
    out = ROOT / 'data' / f'part{partition}.jsonl'
    if out.with_suffix('.json').exists():
        return json.loads(out.with_suffix('.json').read_text())
    db = SCRATCH / 'artifacts/dense.duckdb'
    db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VOLUME_ROOT / 'project/artifacts/data_v3.duckdb', db)
    result = prepare_partition(db, VOLUME_ROOT / 'project/experiments/int003/features',
                               VOLUME_ROOT / 'project/experiments/int003/depth10/mixed.cbm',
                               out, partition)
    volume.commit()
    return result


@app.function(image=gpu_image, volumes={str(VOLUME_ROOT): volume}, cpu=4,
              memory=16384, gpu='L4', timeout=2400)
def fit():
    from ber.dense_training import train
    report = train(ROOT / 'data', ROOT / 'encoder', max_seconds=1800,
                   checkpoint_callback=volume.commit)
    volume.commit()
    return report


@app.function(image=base_image, volumes={str(VOLUME_ROOT): volume}, cpu=4,
              memory=16384, timeout=600)
def error_examples():
    import hashlib
    import numpy as np
    from ber.data import connect
    folder = VOLUME_ROOT / 'project/experiments/int003/depth10'
    meta = json.loads((folder / 'anchors.json').read_text())
    cal = {i for i,m in enumerate(meta) if m['fold'] == 'calibrate'}
    with np.load(folder / 'evaluation.npz') as z:
        g,t,p,y = z['groups'],z['target'],z['prob'],z['y']
    keep = np.isin(g,list(cal))
    candidates = {i:set() for i in cal}
    for group,target in zip(g[keep],t[keep]):
        candidates[int(group)].add(str(target))
    selected = []
    for category, mask, descending in [('false_positive',keep & (y==0) & (p>=.625),True),
                                        ('false_negative',keep & (y==1) & (p<.625),False)]:
        indices = np.flatnonzero(mask)
        order = np.argsort(p[indices])
        if descending:
            order = order[::-1]
        for j in indices[order[:12]]:
            selected.append({'kind':category,'anchor':meta[int(g[j])]['id'],
                             'target':str(t[j]),'probability':float(p[j])})
    missing = [(i,target) for i in cal for target in set(meta[i]['truth'])-candidates[i]]
    missing.sort(key=lambda pair:hashlib.sha256((meta[pair[0]]['id']+pair[1]).encode()).digest())
    for i,target in missing[:16]:
        selected.append({'kind':'not_retrieved','anchor':meta[i]['id'],'target':target})
    ids = sorted({i for row in selected for i in (row['anchor'],row['target'])})
    c = connect(VOLUME_ROOT / 'project/artifacts/data_v3.duckdb')
    records = {i:{'name':n,'address':a,'country':co} for i,n,a,co in c.execute('''
        SELECT entity_id,business_name,business_address,country FROM train
        WHERE entity_id IN (SELECT unnest(?))''',[ids]).fetchall()}
    for row in selected:
        row['left'] = records[row['anchor']]
        row['right'] = records[row['target']]
    c.close()
    return selected


@app.local_entrypoint()
def main(action: str = 'train'):
    if action == 'errors':
        rows = error_examples.remote()
        out = Path('artifacts/int005/error_examples.json')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Saved {len(rows)} private error examples to {out}', flush=True)
        return
    if action != 'train':
        raise ValueError('Unknown action')
    calls = [prepare.spawn(i) for i in range(8)]
    for call in calls:
        print(json.dumps(call.get()), flush=True)
    report = fit.remote()
    Path('reports/int005_training.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
