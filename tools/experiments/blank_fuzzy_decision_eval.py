"""Evaluate blank-address fuzzy rescue against cached capped-pool decisions."""

from collections import defaultdict
from pathlib import Path
import json

import duckdb
import numpy as np
from rapidfuzz import fuzz


def metric(pred, truth, anchors):
    total=0.
    for a in anchors:
        p=pred.get(a,set()); y=truth.get(a,set())
        if not y:
            total += float(not p)
        else:
            tp=len(p&y); fp=len(p-y); fn=len(y-p)
            total += 1.25*tp/(1.25*tp+fp+.25*fn)
    return total/len(anchors)


def main():
    root=Path('artifacts/capped_pairs')
    with np.load(root/'local_decisions.npz') as z:
        keys=list(zip(map(str,z['anchor']),map(str,z['target'])))
        selected={k for k,v in zip(keys,z['chosen']) if v}
    pairs=[]; fold_of={}
    for path in sorted(root.glob('*.jsonl')):
        fold='calibrate' if path.stem.endswith('cal') else 'holdout'
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line)
                a,t=row['anchor'],row['target']
                pairs.append((a,t,fold))
                if a in fold_of and fold_of[a]!=fold: raise ValueError(a)
                fold_of[a]=fold
    if set(keys)!={(a,t) for a,t,_ in pairs}: raise ValueError('Pair coverage mismatch')
    needed=sorted({i for a,t,_ in pairs for i in (a,t)})
    c=duckdb.connect('artifacts/data.duckdb',read_only=True)
    c.execute('CREATE TEMP TABLE needed AS SELECT unnest(?) entity_id',[needed])
    records={i:(country,n,a) for i,country,n,a in c.execute('''SELECT t.entity_id,t.country,t.n,t.a
        FROM train t JOIN needed USING(entity_id)''').fetchall()}
    unique_names=set(c.execute('''SELECT country,n FROM train WHERE source=1 AND n<>''
        GROUP BY 1,2 HAVING count(*)=1''').fetchall())
    truth=defaultdict(set)
    for a,t in c.execute('''SELECT e.anchor,e.target FROM edges e
        JOIN needed n ON n.entity_id=e.anchor''').fetchall():
        truth[a].add(t)
    anchors={f:[a for a,fold in fold_of.items() if fold==f]
             for f in ('calibrate','holdout')}
    baseline=defaultdict(set)
    for a,t in selected: baseline[a].add(t)
    groups=defaultdict(list)
    for a,t,fold in pairs:
        tc,tn,ta=records[t]; ac,an,_=records[a]
        if tc!=ac or ta or not tn: continue
        exact=an==tn and (ac,an) in unique_names
        if exact: baseline[a].add(t)
        groups[fold,t].append((a, fuzz.ratio(an,tn),
                               fuzz.token_sort_ratio(an,tn),
                               fuzz.token_set_ratio(an,tn),
                               (ac,an) in unique_names))
    base_scores={f:metric(baseline,truth,anchors[f]) for f in anchors}
    claimed={f:set() for f in anchors}
    for a,ts in baseline.items():
        claimed[fold_of[a]].update(ts)
    results=[]
    for kind,index in [('ratio',1),('token_sort',2),('token_set',3)]:
      for minimum in (80,85,90,95,98):
       for margin in (0,5,10,15):
        for skip_claimed in (False,True):
         additions={f:defaultdict(set) for f in anchors}
         counts={f:{'true':0,'false':0} for f in anchors}
         for (fold,t),members in groups.items():
            if skip_claimed and t in claimed[fold]: continue
            ranked=sorted(members,key=lambda r:r[index],reverse=True)
            winner=ranked[0]
            second=ranked[1][index] if len(ranked)>1 else 0
            if winner[index]<minimum or winner[index]-second<margin or not winner[4]:
                continue
            a=winner[0]
            if t in baseline[a]: continue
            additions[fold][a].add(t)
            counts[fold]['true' if t in truth[a] else 'false']+=1
         scores={fold:metric({a:baseline[a]|additions[fold][a] for a in anchors[fold]},truth,anchors[fold])
                 for fold in anchors}
         results.append({'rule':f'{kind}_{minimum}_{margin}_skip{int(skip_claimed)}',
                         'counts':counts,'scores':scores,
                         'deltas':{f:scores[f]-base_scores[f] for f in anchors}})
    top=sorted(results,key=lambda x:x['scores']['calibrate'],reverse=True)[:15]
    report={'baseline_scores':base_scores,'blank_groups':len(groups),
            'top_calibration_rules':top,'all_rules':results}
    Path('reports/blank_fuzzy_decision_eval.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'baseline_scores':base_scores,'top_calibration_rules':top},indent=2))


if __name__=='__main__': main()
