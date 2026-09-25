"""A separate confirmation sample excluded from model fitting and cap selection."""
import argparse
import json
from pathlib import Path
import numpy as np
from catboost import CatBoostClassifier
from .blocking import candidates
from .data import connect
from .metrics import evaluate,row_score
from .predict import score_batch


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=Path('artifacts/data.duckdb'))
    p.add_argument('--model',type=Path,default=Path('artifacts/address_baseline'))
    p.add_argument('--report',type=Path,default=Path('reports/confirmation.json'))
    p.add_argument('--offset',type=int,default=30000)
    p.add_argument('--size',type=int,default=5000)
    a=p.parse_args()
    config=json.loads((a.model/'model_config.json').read_text())
    c=connect(a.db)
    c.execute(f'''CREATE OR REPLACE TEMP TABLE confirm_anchors AS SELECT * FROM train WHERE source=1
        ORDER BY md5('sample517:'||entity_id) LIMIT {a.size} OFFSET {a.offset}''')
    training_ids={m['id'] for m in json.loads((a.model/'anchors.json').read_text())}
    truth_rows=c.execute('''SELECT a.entity_id,a.country,t.matches FROM confirm_anchors a
        JOIN truth t ON a.entity_id=t.anchor''').fetchall()
    if any(r[0] in training_ids for r in truth_rows):
        raise ValueError('Confirmation sample overlaps development anchors')
    candidates(c,'train','confirm_anchors','confirm_candidates',config['candidate_cap'])
    model=CatBoostClassifier()
    model.load_model(str(a.model/'mixed.cbm'))
    predicted,considered=score_batch(c,model,config['threshold'],'train','confirm_anchors','confirm_candidates',config.get('shortlist_cap'))
    result={'protocol':'Separate hash-ordered anchors, excluded from fitting, early stopping, calibration, and candidate-budget selection',
            'size':a.size,'offset':a.offset,'config':config,'scores':{}}
    for country in [None]+sorted({r[1] for r in truth_rows}):
        truth={i:matches.split(',') if matches else [] for i,co,matches in truth_rows if country is None or country==co}
        metrics=evaluate(truth,predicted,considered)
        scores=np.array([row_score(t,predicted[i]) for i,t in truth.items()])
        rng=np.random.default_rng(517)
        boot=rng.choice(scores,size=(1000,len(scores)),replace=True).mean(axis=1)
        metrics['bootstrap_95_percent_interval']=np.quantile(boot,[.025,.975]).tolist()
        result['scores'][country or 'all']=metrics
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    c.close()
    print(json.dumps(result['scores'],indent=2))


if __name__=='__main__':
    main()
