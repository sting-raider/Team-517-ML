"""Evaluate target-to-target evidence for missed blank-address links."""

from collections import defaultdict
from pathlib import Path
import json

import duckdb
import numpy as np
from rapidfuzz import fuzz

from blank_fuzzy_decision_eval import metric


def main():
    root=Path('artifacts/capped_pairs')
    with np.load(root/'local_decisions.npz') as z:
        keys=list(zip(map(str,z['anchor']),map(str,z['target'])))
        chosen={k for k,p in zip(keys,z['chosen']) if p}
    pairs=[]; fold_of={}
    for path in sorted(root.glob('*.jsonl')):
        fold='calibrate' if path.stem.endswith('cal') else 'holdout'
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line)
                a,t=row['anchor'],row['target']
                pairs.append((a,t))
                fold_of[a]=fold
    needed=sorted({i for pair in pairs for i in pair})
    c=duckdb.connect('artifacts/data.duckdb',read_only=True)
    c.execute('CREATE TEMP TABLE needed AS SELECT unnest(?) entity_id',[needed])
    rec={i:(country,source,n,a) for i,country,source,n,a in c.execute('''
        SELECT t.entity_id,t.country,t.source,t.n,t.a FROM train t JOIN needed USING(entity_id)''').fetchall()}
    unique_names=set(c.execute('''SELECT country,n FROM train WHERE source=1 AND n<>''
        GROUP BY 1,2 HAVING count(*)=1''').fetchall())
    truth=defaultdict(set)
    for a,t in c.execute('''SELECT e.anchor,e.target FROM edges e JOIN needed n
        ON n.entity_id=e.anchor''').fetchall(): truth[a].add(t)
    baseline=defaultdict(set)
    for a,t in chosen: baseline[a].add(t)
    for a,t in pairs:
        co,_,tn,ta=rec[t]; _,_,an,_=rec[a]
        if not ta and tn and tn==an and (co,an) in unique_names:
            baseline[a].add(t)
    anchors={f:[a for a,fold in fold_of.items() if fold==f]
             for f in ('calibrate','holdout')}
    baseline_score={f:metric(baseline,truth,anchors[f]) for f in anchors}
    candidates=[]
    for a,t in pairs:
        if t in baseline[a] or rec[t][3] or not rec[t][2]: continue
        siblings=[s for s in baseline[a] if s!=t and rec[s][2]]
        if not siblings: continue
        scores=[]
        for s in siblings:
            scores.append((fuzz.ratio(rec[t][2],rec[s][2]),
                           fuzz.token_sort_ratio(rec[t][2],rec[s][2]),
                           fuzz.token_set_ratio(rec[t][2],rec[s][2]),
                           rec[t][1]!=rec[s][1]))
        candidates.append((a,t,scores))
    results=[]
    for metric_name,index in [('ratio',0),('token_sort',1),('token_set',2)]:
      for minimum in (70,80,85,90,95,98,100):
       for opposite in (False,True):
        additions=defaultdict(set)
        counts={f:{'true':0,'false':0} for f in anchors}
        for a,t,scores in candidates:
            if any(s[index]>=minimum and (not opposite or s[3]) for s in scores):
                additions[a].add(t)
                counts[fold_of[a]]['true' if t in truth[a] else 'false']+=1
        adjusted={a:baseline[a]|additions[a] for a in fold_of}
        scored={f:metric(adjusted,truth,anchors[f]) for f in anchors}
        results.append({'rule':f'{metric_name}_{minimum}_opposite{int(opposite)}',
                        'counts':counts,'score':scored,
                        'delta':{f:scored[f]-baseline_score[f] for f in anchors}})
    top=sorted(results,key=lambda r:r['score']['calibrate'],reverse=True)[:12]
    report={'baseline':baseline_score,'eligible_candidate_pairs':len(candidates),
            'top_calibration_rules':top,'all_rules':results}
    Path('reports/sibling_name_recovery_eval.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='all_rules'},indent=2))


if __name__=='__main__':main()
