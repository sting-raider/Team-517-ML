"""Coordinator's measured submission-v2 experiments on the private Modal Volume."""
import json
import shutil
from pathlib import Path
import modal
from modal_app import image, volume, _enable_native_features, SCRATCH, VOLUME_ROOT
image=image.add_local_python_source('modal_app')

app=modal.App('team517-v2')
RUN_ROOT=VOLUME_ROOT/'project/experiments/int002'


def copy_database():
    dest=SCRATCH/'artifacts/data.duckdb'
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(VOLUME_ROOT/'project/artifacts/data.duckdb',dest)
    return dest


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=32768,timeout=3600)
def make_features(partition:int,partitions:int=8,confirmation:bool=False):
    base=RUN_ROOT/('confirmation' if confirmation else 'features')
    out=base/f'part{partition}'
    if (out/'ready.json').exists():
        from ber.v2 import V2_NAMES
        receipt=json.loads((out/'ready.json').read_text())
        if (receipt['feature_names']!=V2_NAMES or receipt['partitions']!=partitions
                or receipt['partition']!=partition or receipt['confirmation']!=confirmation):
            raise ValueError('Feature cache does not match the requested run')
        return receipt
    _enable_native_features()
    from ber.v2 import materialize
    db=copy_database()
    result=materialize(db,out,partition,partitions,confirmation=confirmation)
    volume.commit()
    return result


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=65536,gpu='L4',timeout=3600)
def train_model(depth:int=8):
    from ber.v2 import train
    out=RUN_ROOT/f'depth{depth}'
    result=train(RUN_ROOT/'features',out,VOLUME_ROOT/'project/artifacts/submission_v1',depth=depth)
    volume.commit()
    return result


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=32768,timeout=3600)
def retrieval_study():
    from ber.retrieval_v3 import experiment
    result=experiment(copy_database(),RUN_ROOT/'retrieval_report.json')
    volume.commit()
    return result


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=16384,timeout=1800)
def confirm_model(depth:int):
    import numpy as np
    from catboost import CatBoostClassifier
    from ber.v2 import load_parts,score_slices
    from ber.features import FEATURE_NAMES
    from ber.predict import sha256
    x,y,g,t,meta=load_parts(RUN_ROOT/'confirmation',1)
    folder=RUN_ROOT/f'depth{depth}'
    config=json.loads((folder/'model_config.json').read_text())
    model=CatBoostClassifier();model.load_model(str(folder/'mixed.cbm'))
    p=model.predict_proba(x,thread_count=8)[:,1]
    old=CatBoostClassifier();old.load_model(str(VOLUME_ROOT/'project/artifacts/submission_v1/mixed.cbm'))
    bp=old.predict_proba(x[:,:len(FEATURE_NAMES)],thread_count=8)[:,1]
    result={'protocol':'5000 anchors at hash positions 40001:45000, excluded from INT002 fitting and selection; other swarm S1 audits inspected full training labels',
        'depth':depth,'config':config,
        'model_sha256':sha256(folder/'mixed.cbm'),
        'baseline':score_slices(meta,g,t,bp,'confirmation',.5750000000000002),
        'new':score_slices(meta,g,t,p,'confirmation',config['threshold'])}
    from ber.experiment import mappings
    from ber.metrics import row_score
    truth,pred,_=mappings(meta,g,t,p,range(len(meta)),config['threshold'])
    _,prior,_=mappings(meta,g,t,bp,range(len(meta)),.5750000000000002)
    delta=np.array([row_score(truth[k],pred[k])-row_score(truth[k],prior[k]) for k in truth])
    rng=np.random.default_rng(517)
    boot=np.array([rng.choice(delta,size=len(delta),replace=True).mean() for _ in range(2000)])
    result['paired_comparison']={'delta':float(delta.mean()),
        'bootstrap_95_interval':np.quantile(boot,[.025,.975]).tolist(),
        'improved_entities':int((delta>0).sum()),'regressed_entities':int((delta<0).sum()),
        'bootstrap_resamples':2000,'seed':517}
    (folder/'confirmation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    volume.commit();return result


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=32768,timeout=3600)
def score_partition(depth:int,partition:int,partitions:int=8):
    import threading
    _enable_native_features()
    from ber.predict import predict
    db=copy_database();out=VOLUME_ROOT/'project/output'/f'submission_v2_d{depth}_part{partition}of{partitions}'
    stop=threading.Event()
    def checkpoint():
        while not stop.wait(180):
            volume.commit()
    writer=threading.Thread(target=checkpoint,daemon=True);writer.start()
    try:
        predict(db,RUN_ROOT/f'depth{depth}',out,batch_size=10000,workers=8,query_batches=1,
                partition_index=partition,partition_count=partitions)
    finally:
        stop.set();writer.join(timeout=30);volume.commit()
    return str(out)


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=4,memory=16384,timeout=1800)
def merge_prediction(depth:int,partitions:int=8):
    from modal_app import merge_score
    return merge_score.local(f'submission_v2_d{depth}',partitions,160)


@app.local_entrypoint()
def main(action:str='train',depth:int=10):
    if action=='train':
        calls=[make_features.spawn(i) for i in range(8)]
        for i,call in enumerate(calls):
            print(f'Feature partition {i}: {call.get()}',flush=True)
        calls=[(d,train_model.spawn(d)) for d in (depth,)]
        for d,call in calls:
            report=call.get()
            path=Path('reports')/f'int002_depth{d}.json'
            path.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(f'Depth {d} report: {path}',flush=True)
    elif action=='fit':
        report=train_model.remote(depth)
        Path(f'reports/int002_depth{depth}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    elif action=='retrieval':
        report=retrieval_study.remote()
        Path('reports/int002_retrieval.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    elif action=='prepare-confirmation':
        print(make_features.remote(0,1,True))
    elif action=='confirm':
        make_features.remote(0,1,True)
        result=confirm_model.remote(depth)
        Path(f'reports/int002_depth{depth}_confirmation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    elif action=='score':
        calls=[score_partition.spawn(depth,i) for i in range(8)]
        for call in calls:
            print(call.get(),flush=True)
        result=merge_prediction.remote(depth)
        Path(f'reports/int002_depth{depth}_export.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    else:
        raise ValueError('Unknown action')
