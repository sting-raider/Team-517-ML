"""Stronger learned matchers; calibration selects quality without a speed tolerance."""
import argparse
import json
from pathlib import Path
import numpy as np
from catboost import CatBoostClassifier
from .experiment import choose_threshold,mappings
from .metrics import evaluate
from .provenance import StaleArtifactError,files_signature,read_manifest,require_manifest,write_manifest


TUNE_CACHE_VERSION=1
TRAIN_INPUTS=[
    Path('artifacts/address_baseline/features.npz'),
    Path('artifacts/address_baseline/anchors.json'),
    Path('artifacts/address_baseline/features.manifest.json'),
    Path('artifacts/wide_calibration/features.npz'),
    Path('artifacts/wide_calibration/anchors.json'),
    Path('artifacts/wide_calibration/features.manifest.json'),
]


def trial_identity(depth):
    return {
        'kind':'catboost_tune_trial',
        'version':TUNE_CACHE_VERSION,
        'depth':depth,
        'params':{
            'iterations':1500,'learning_rate':.045,'loss_function':'Logloss',
            'l2_leaf_reg':10,'random_seed':517,'early_stopping_rounds':100,
        },
        'inputs':files_signature(TRAIN_INPUTS),
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--refresh',action='store_true',
                   help='Retrain even when compatible completed trial artifacts exist')
    a=p.parse_args()
    out=Path('artifacts/tuned');out.mkdir(parents=True,exist_ok=True)
    for manifest in (
        Path('artifacts/address_baseline/features.manifest.json'),
        Path('artifacts/wide_calibration/features.manifest.json'),
    ):
        if read_manifest(manifest) is None:
            raise StaleArtifactError(
                f'Cannot tune from unsigned feature cache {manifest}; rebuild the feature cache first'
            )
    base=np.load('artifacts/address_baseline/features.npz')
    x,y,groups=(base[k] for k in ('x','y','groups'))
    meta=json.loads(Path('artifacts/address_baseline/anchors.json').read_text())
    wide=np.load('artifacts/wide_calibration/features.npz')
    wx,wg,wt=(wide[k] for k in ('x','groups','target'))
    wm=json.loads(Path('artifacts/wide_calibration/anchors.json').read_text())
    fit=np.isin(groups,[i for i,m in enumerate(meta) if m['fold']=='fit'])
    early=np.isin(groups,[i for i,m in enumerate(meta) if m['fold']=='early'])
    counts=np.bincount(groups,minlength=len(meta))
    weights=1/np.maximum(1,counts[groups[fit]]);weights/=weights.mean()
    report=json.loads(Path('reports/tuning.json').read_text()) if Path('reports/tuning.json').exists() else {}
    for depth in (8,10):
        name=f'depth{depth}'
        identity=trial_identity(depth)
        complete=name in report and (out/f'{name}.cbm').exists() and (out/f'{name}_wide_probabilities.npy').exists()
        if complete and not a.refresh:
            require_manifest(out/f'{name}.manifest.json',identity,f'{name} tuning trial')
            print(f'Reusing compatible {name} trial',flush=True)
            continue
        model=CatBoostClassifier(iterations=1500,depth=depth,learning_rate=.045,loss_function='Logloss',
            l2_leaf_reg=10,random_seed=517,thread_count=6,verbose=200,allow_writing_files=False)
        model.fit(x[fit],y[fit],sample_weight=weights,eval_set=(x[early],y[early]),early_stopping_rounds=100)
        pwide=model.predict_proba(wx,thread_count=6)[:,1]
        threshold,_=choose_threshold(wm,wg,wt,pwide,range(len(wm)))
        truth,pred,cand=mappings(wm,wg,wt,pwide,range(len(wm)),threshold)
        report[name]={'threshold':threshold,'trees':model.tree_count_,**evaluate(truth,pred,cand)}
        model.save_model(str(out/f'{name}.cbm'))
        np.save(out/f'{name}_wide_probabilities.npy',pwide)
        write_manifest(out/f'{name}.manifest.json',identity)
        Path('reports/tuning.json').write_text(json.dumps(report,indent=2))
        print(name,json.dumps(report[name]),flush=True)


if __name__=='__main__':
    main()
