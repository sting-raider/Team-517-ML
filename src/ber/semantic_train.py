"""A controlled CatBoost ablation adding local multilingual cosine features."""
import argparse
import json
from pathlib import Path
import numpy as np
from catboost import CatBoostClassifier
from .experiment import choose_threshold,mappings
from .metrics import evaluate
from .features import FEATURE_NAMES


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--fields',nargs='+',choices=['name','record'],default=['name'])
    a=p.parse_args()
    name='semantic_'+'_'.join(a.fields)
    out=Path('artifacts/tuned');out.mkdir(parents=True,exist_ok=True)
    f=np.load('artifacts/address_baseline/features.npz')
    y,groups=f['y'],f['groups']
    x=np.column_stack([f['x']]+[np.load(f'artifacts/semantic/{field}_address_baseline_cosine.npy') for field in a.fields])
    meta=json.loads(Path('artifacts/address_baseline/anchors.json').read_text())
    w=np.load('artifacts/wide_calibration/features.npz')
    wx=np.column_stack([w['x']]+[np.load(f'artifacts/semantic/{field}_wide_calibration_cosine.npy') for field in a.fields])
    wg,wt=w['groups'],w['target']
    wm=json.loads(Path('artifacts/wide_calibration/anchors.json').read_text())
    fit=np.isin(groups,[i for i,m in enumerate(meta) if m['fold']=='fit'])
    early=np.isin(groups,[i for i,m in enumerate(meta) if m['fold']=='early'])
    counts=np.bincount(groups,minlength=len(meta))
    weights=1/np.maximum(1,counts[groups[fit]]);weights/=weights.mean()
    model=CatBoostClassifier(iterations=1500,depth=8,learning_rate=.045,loss_function='Logloss',
        l2_leaf_reg=10,random_seed=517,thread_count=6,verbose=200,allow_writing_files=False)
    model.fit(x[fit],y[fit],sample_weight=weights,eval_set=(x[early],y[early]),early_stopping_rounds=100)
    prob=model.predict_proba(wx,thread_count=6)[:,1]
    threshold,curve=choose_threshold(wm,wg,wt,prob,range(len(wm)))
    report={'fields':a.fields,'threshold':threshold,'trees':model.tree_count_,'calibration_curve':curve,'scores':{}}
    for country in [None]+sorted({m['country'] for m in wm}):
        chosen=[i for i,m in enumerate(wm) if country is None or m['country']==country]
        truth,pred,cand=mappings(wm,wg,wt,prob,chosen,threshold)
        report['scores'][country or 'all']=evaluate(truth,pred,cand)
    names=FEATURE_NAMES+[f'e5_{field}_cosine' for field in a.fields]
    report['feature_importance']=dict(sorted(zip(names,map(float,model.feature_importances_)),key=lambda kv:-kv[1]))
    model.save_model(str(out/f'{name}.cbm'))
    np.save(out/f'{name}_wide_probabilities.npy',prob)
    Path(f'reports/{name}.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report['scores'],indent=2))


if __name__=='__main__':
    main()
