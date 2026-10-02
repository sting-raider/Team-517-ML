"""Identify which held-out anchors benefit from the production stacker."""

from collections import defaultdict
import json

from catboost import CatBoostClassifier
import duckdb
import numpy as np

from ber.features import features


def main():
    with np.load('artifacts/capped_pairs/local_decisions.npz') as z:
        anchors=np.array(list(map(str,z['anchor'])))
        targets=np.array(list(map(str,z['target'])))
        fold=np.array(list(map(str,z['fold'])))
        cross=z['cross']; cat=z['cat']; fused=z['fused']
        dense=z['dense']; y=z['truth']; chosen=z['chosen']
    con=duckdb.connect('artifacts/data.duckdb',read_only=True)
    needed=sorted(set(anchors)|set(targets))
    con.execute('CREATE TEMP TABLE needed AS SELECT unnest(?) entity_id',[needed])
    records={i:(c,int(s),n,a) for i,c,s,n,a in con.execute('''SELECT t.entity_id,
        t.country,t.source,t.n,t.a FROM train t JOIN needed USING(entity_id)''').fetchall()}
    unique_names=set(con.execute('''SELECT country,n FROM train WHERE source=1 AND n<>''
        GROUP BY 1,2 HAVING count(*)=1''').fetchall())
    aux=np.asarray([features(records[a][2],records[a][3],records[t][2],
                             records[t][3],0,0,records[t][1]) for a,t in zip(anchors,targets)],np.float32)
    catlog=np.log(np.clip(cat,1e-7,1-1e-7)/(1-np.clip(cat,1e-7,1-1e-7)))
    X=np.column_stack([cross,catlog,fused,dense.astype(np.float32),aux]).astype(np.float32)
    model=CatBoostClassifier()
    model.load_model('artifacts/capped_pairs/stacker_final.cbm')
    probability=model.predict_proba(X)[:,1]
    stack=probability>=.8
    blank=np.array([bool(records[t][3]=='') and bool(records[t][2]) and
                    records[a][2]==records[t][2] and
                    (records[a][0],records[a][2]) in unique_names
                    for a,t in zip(anchors,targets)],bool)
    v6=chosen|blank
    ids=sorted(set(anchors))
    gid={a:i for i,a in enumerate(ids)}
    con.execute('CREATE TEMP TABLE sampled AS SELECT unnest(?) anchor',[ids])
    truth_count={a:0 for a in ids}
    for a,n in con.execute('''SELECT e.anchor,count(*) FROM edges e JOIN sampled s USING(anchor)
        GROUP BY 1''').fetchall(): truth_count[a]=n
    rows=defaultdict(lambda: {'tp6':0,'p6':0,'tps':0,'ps':0,'truth':0,
                              'blank_candidates':0})
    fold_of=dict(zip(anchors,fold))
    for a,t,actual,base,new,ta in zip(anchors,targets,y,v6,stack,
                                      [records[t][3] for t in targets]):
        row=rows[a]
        row['tp6']+=bool(actual and base)
        row['p6']+=bool(base)
        row['tps']+=bool(actual and new)
        row['ps']+=bool(new)
        row['blank_candidates']+=not bool(ta)
    output={}
    for category,predicate in [
        ('all',lambda a,r:True),
        ('India',lambda a,r:records[a][0]=='India'),
        ('US',lambda a,r:records[a][0]=='US'),
        ('V6_empty',lambda a,r:r['p6']==0),
        ('V6_nonempty',lambda a,r:r['p6']>0),
        ('blank_candidate',lambda a,r:r['blank_candidates']>0),
        ('no_blank_candidate',lambda a,r:r['blank_candidates']==0),
        ('V6_one',lambda a,r:r['p6']==1),
        ('V6_many',lambda a,r:r['p6']>=4)]:
        subset=[(a,r) for a,r in rows.items() if fold_of[a]=='holdout' and predicate(a,r)]
        def each(a,r,key_tp,key_p):
            tc=truth_count[a]; tp=r[key_tp]; fp=r[key_p]-tp; fn=tc-tp
            return float(r[key_p]==0) if tc==0 else 1.25*tp/(1.25*tp+fp+.25*fn)
        score6=np.mean([each(a,r,'tp6','p6') for a,r in subset])
        scores=np.mean([each(a,r,'tps','ps') for a,r in subset])
        output[category]={'anchors':len(subset),'v6':float(score6),'stacker':float(scores),
                          'gain':float(scores-score6)}
    print(json.dumps(output,indent=2))
    with open('reports/stacker_slice_eval.json','w',encoding='utf-8') as stream:
        json.dump(output,stream,indent=2)


if __name__=='__main__':main()
