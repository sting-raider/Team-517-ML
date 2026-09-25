"""Coordinator's measured submission-v2 experiments on the private Modal Volume."""
import json
import shutil
from pathlib import Path
import modal
from modal_app import image, volume, _enable_native_features, SCRATCH, VOLUME_ROOT
image=image.add_local_python_source('modal_app')

app=modal.App('team517-v2')
RUN_ROOT=VOLUME_ROOT/'project/experiments/int001'


def copy_database():
    dest=SCRATCH/'artifacts/data.duckdb'
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(VOLUME_ROOT/'project/artifacts/data.duckdb',dest)
    return dest


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=32768,timeout=3600)
def make_features(partition:int,partitions:int=8,confirmation:bool=False):
    _enable_native_features()
    from ber.v2 import materialize
    db=copy_database()
    base=RUN_ROOT/('confirmation' if confirmation else 'features')
    out=base/f'part{partition}'
    if (out/'ready.json').exists():
        return json.loads((out/'ready.json').read_text())
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
    x,y,g,t,meta=load_parts(RUN_ROOT/'confirmation',1)
    folder=RUN_ROOT/f'depth{depth}'
    config=json.loads((folder/'model_config.json').read_text())
    model=CatBoostClassifier();model.load_model(str(folder/'mixed.cbm'))
    p=model.predict_proba(x,thread_count=8)[:,1]
    old=CatBoostClassifier();old.load_model(str(VOLUME_ROOT/'project/artifacts/submission_v1/mixed.cbm'))
    bp=old.predict_proba(x[:,:len(FEATURE_NAMES)],thread_count=8)[:,1]
    result={'protocol':'5000 anchors at hash positions 40001:45000, excluded from INT001 fitting and selection; other swarm S1 audits inspected full training labels',
        'depth':depth,'config':config,
        'baseline':score_slices(meta,g,t,bp,'confirmation',.5750000000000002),
        'new':score_slices(meta,g,t,p,'confirmation',config['threshold'])}
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
def main(action:str='train',depth:int=8):
    if action=='train':
        calls=[make_features.spawn(i) for i in range(8)]
        for i,call in enumerate(calls):
            print(f'Feature partition {i}: {call.get()}',flush=True)
        calls=[(d,train_model.spawn(d)) for d in (8,10)]
        for d,call in calls:
            report=call.get()
            path=Path('reports')/f'int001_depth{d}.json'
            path.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(f'Depth {d} report: {path}',flush=True)
    elif action=='fit':
        report=train_model.remote(depth)
        Path(f'reports/int001_depth{depth}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    elif action=='retrieval':
        report=retrieval_study.remote()
        Path('reports/int001_retrieval.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    elif action=='confirm':
        make_features.remote(0,1,True)
        result=confirm_model.remote(depth)
        Path(f'reports/int001_depth{depth}_confirmation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    elif action=='score':
        calls=[score_partition.spawn(depth,i) for i in range(8)]
        for call in calls:
            print(call.get(),flush=True)
        result=merge_prediction.remote(depth)
        Path(f'reports/int001_depth{depth}_export.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    else:
        raise ValueError('Unknown action')
