"""Choose a deployment retrieval cap using calibration anchors only."""
import argparse
import json
from pathlib import Path
import numpy as np
from .experiment import choose_threshold,mappings
from .metrics import evaluate
from .shortlist import shortlist_mask


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--model',type=Path,default=Path('artifacts/address_baseline'))
    p.add_argument('--report',type=Path,default=Path('reports/cap_study.json'))
    p.add_argument('--select-tolerance',type=float,help='Select fastest median candidate count within this calibration-score loss of the best')
    a=p.parse_args()
    f=np.load(a.model/'features.npz')
    x,groups,target=(f[k] for k in ('x','groups','target'))
    prob=np.load(a.model/'mixed_probabilities.npy')
    meta=json.loads((a.model/'anchors.json').read_text())
    order=np.lexsort((target,-x[:,-3],groups))
    ordered_groups=groups[order]
    starts=np.r_[0,np.flatnonzero(np.diff(ordered_groups))+1]
    lengths=np.diff(np.r_[starts,len(order)])
    rank=np.empty(len(order),dtype=int)
    rank[order]=np.arange(len(order))-np.repeat(starts,lengths)+1
    calibrate=[i for i,m in enumerate(meta) if m['fold']=='calibrate']
    report={}
    for mode in ('retrieval','lexical'):
        for cap in (10,20,30,40,60,80):
            keep=rank<=cap if mode=='retrieval' else shortlist_mask(groups,target,
                (x[:,0]+x[:,2])/2,(x[:,22]+x[:,24])/2,(x[:,42]>0)|(x[:,43]>0),cap)
            threshold,_=choose_threshold(meta,groups[keep],target[keep],prob[keep],calibrate)
            truth,pred,candidates=mappings(meta,groups[keep],target[keep],prob[keep],calibrate,threshold)
            report[f'{mode}_{cap}']={'threshold':threshold,**evaluate(truth,pred,candidates)}
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2))
    if a.select_tolerance is not None:
        best=max(v['macro_f0_5'] for v in report.values())
        eligible=[k for k,v in report.items() if k.startswith('lexical_') and v['macro_f0_5']>=best-a.select_tolerance]
        chosen=min(eligible,key=lambda k:(report[k]['candidate_count_quantiles']['p50'],int(k.split('_')[1])))
        config_path=a.model/'model_config.json'
        config=json.loads(config_path.read_text())
        config.update({'shortlist_cap':int(chosen.split('_')[1]),'threshold':report[chosen]['threshold'],
                       'blocker_version':2,'selection':'calibration only','selection_tolerance':a.select_tolerance})
        config_path.write_text(json.dumps(config,indent=2))
        print('Selected '+chosen,flush=True)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
