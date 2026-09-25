"""Measure wider candidate pools and lexical reranking on calibration labels only."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from .data import connect
from .blocking import candidates
from .shortlist import shortlist_mask
from .metrics import evaluate


def main():
    meta=json.loads(Path('artifacts/address_baseline/anchors.json').read_text())
    meta=[m for m in meta if m['fold']=='calibrate']
    lookup={m['id']:i for i,m in enumerate(meta)}
    truth={m['id']:set(m['truth']) for m in meta}
    c=connect('artifacts/data.duckdb')
    c.register('selection',pd.DataFrame({'id':list(lookup)}))
    c.execute('CREATE OR REPLACE TEMP TABLE study_anchors AS SELECT t.* FROM train t JOIN selection s ON t.entity_id=s.id')
    candidates(c,'train','study_anchors','wide_candidates',640)
    count=c.execute('SELECT count(*) FROM wide_candidates').fetchone()[0]
    groups=np.empty(count,dtype=np.int32)
    targets=np.empty(count,dtype='U32')
    name=np.empty(count,dtype=np.float32)
    address=np.empty(count,dtype=np.float32)
    missing=np.empty(count,dtype=bool)
    rank=np.empty(count,dtype=np.int32)
    c.execute('''SELECT p.anchor,r.entity_id,l.n,l.a,r.n,r.a,
        row_number() OVER(PARTITION BY p.anchor ORDER BY p.retrieval DESC,r.entity_id) AS rank
        FROM wide_candidates p JOIN study_anchors l ON p.anchor=l.entity_id
        JOIN train r ON p.rid=r.rowid''')
    pos=0
    while rows:=c.fetchmany(20000):
        for aid,rid,n1,a1,n2,a2,r in rows:
            groups[pos]=lookup[aid]; targets[pos]=rid; rank[pos]=r
            name[pos]=(np.float32(fuzz.ratio(n1,n2)/100)+np.float32(fuzz.token_set_ratio(n1,n2)/100))/np.float32(2)
            address[pos]=(np.float32(fuzz.ratio(a1,a2)/100)+np.float32(fuzz.token_set_ratio(a1,a2)/100))/np.float32(2)
            missing[pos]=not a1 or not a2
            pos+=1
    c.close()
    report={}
    for mode in ('retrieval','lexical'):
        for cap in (80,160,320,640):
            keep=rank<=cap if mode=='retrieval' else shortlist_mask(groups,targets,name,address,missing,cap)
            cand={k:set() for k in truth}
            for g,t in zip(groups[keep],targets[keep]):
                cand[meta[g]['id']].add(str(t))
            stats=evaluate(truth,{},cand)
            stats.pop('macro_f0_5');stats.pop('singleton_false_positive_rate')
            report[f'{mode}_{cap}']=stats
            print(mode,cap,stats['candidate_pair_recall'],stats['blocking_oracle_macro_f0_5'],flush=True)
    Path('reports/retrieval_study.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
