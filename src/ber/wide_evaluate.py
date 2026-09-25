"""Measure actual classifier utility of the wider retrieval pool on calibration."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from .data import connect
from .experiment import materialize,choose_threshold,mappings
from .shortlist import shortlist_mask
from .metrics import evaluate


def main():
    out=Path('artifacts/wide_calibration')
    if not (out/'features.npz').exists():
        meta=json.loads(Path('artifacts/address_baseline/anchors.json').read_text())
        selected=[m['id'] for m in meta if m['fold']=='calibrate']
        c=connect('artifacts/data.duckdb')
        c.register('selection',pd.DataFrame({'id':selected}))
        c.execute('CREATE OR REPLACE TABLE wide_anchors AS SELECT t.* FROM train t JOIN selection s ON t.entity_id=s.id')
        c.close()
        x,y,groups,target,meta=materialize('artifacts/data.duckdb',out,'wide_anchors','wide_candidates')
    else:
        f=np.load(out/'features.npz')
        x,y,groups,target=(f[k] for k in ('x','y','groups','target'))
        meta=json.loads((out/'anchors.json').read_text())
    model=CatBoostClassifier()
    model.load_model('artifacts/address_baseline/mixed.cbm')
    prob=model.predict_proba(x,thread_count=6)[:,1]
    np.save(out/'base_probabilities.npy',prob)
    order=np.lexsort((target,-x[:,-3],groups))
    starts=np.r_[0,np.flatnonzero(np.diff(groups[order]))+1]
    rank=np.empty(len(order),dtype=int)
    rank[order]=np.arange(len(order))-np.repeat(starts,np.diff(np.r_[starts,len(order)]))+1
    report={}
    for mode in ('retrieval','lexical'):
        for cap in (80,160,320,640):
            keep=rank<=cap if mode=='retrieval' else shortlist_mask(groups,target,
                (x[:,0]+x[:,2])/2,(x[:,22]+x[:,24])/2,(x[:,42]>0)|(x[:,43]>0),cap)
            threshold,_=choose_threshold(meta,groups[keep],target[keep],prob[keep],range(len(meta)))
            truth,pred,cand=mappings(meta,groups[keep],target[keep],prob[keep],range(len(meta)),threshold)
            report[f'{mode}_{cap}']={'threshold':threshold,**evaluate(truth,pred,cand)}
            print(mode,cap,report[f'{mode}_{cap}']['macro_f0_5'],flush=True)
    Path('reports/wide_calibration.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
