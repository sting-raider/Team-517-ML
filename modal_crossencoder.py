"""M017 train multilingual pair reranker on frozen INT003 fit examples."""
import json
from pathlib import Path

import modal
from modal_app import volume,VOLUME_ROOT

image=(modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent/'requirements.txt'))
    .pip_install('torch==2.8.0','transformers==4.57.1',
                 'huggingface_hub==0.36.0','sentencepiece==0.2.1')
    .env({'PYTHONPATH':'/app/src'})
    .add_local_dir(str(Path(__file__).parent/'src'),'/app/src')
    .add_local_python_source('modal_app'))
app=modal.App('team517-m017-crossencoder')
ROOT=VOLUME_ROOT/'project/experiments/m017'
BASE=VOLUME_ROOT/'project/experiments/int003/depth10'


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=24576,gpu='L4',timeout=3600)
def fit():
    from ber.crossencoder import train
    report=train(VOLUME_ROOT/'project/experiments/int005/data',ROOT/'model',
                 max_seconds=3200,callback=volume.commit)
    volume.commit()
    return report


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=16384,gpu='L4',timeout=1800)
def score(fold:str,part:int):
    from ber.crossencoder import score_partition
    result=score_partition(VOLUME_ROOT/'project/artifacts/data_v3.duckdb',
                           BASE,ROOT/'model',ROOT/'scores'/f'{fold}_part{part}.npz',
                           fold,part)
    volume.commit()
    return result


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=8192,timeout=600)
def evaluate():
    from ber.crossencoder import evaluate_pair_model
    result=evaluate_pair_model(BASE,ROOT/'scores',ROOT/'evaluation.json')
    volume.commit()
    return result


@app.local_entrypoint()
def main(action:str='train'):
    if action=='train':
        report=fit.remote()
        Path('reports/m017_training.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2),flush=True)
        return
    if action!='evaluate':
        raise ValueError('Expected train or evaluate')
    for fold in ('calibrate','holdout'):
        calls=[score.spawn(fold,p) for p in range(8)]
        for call in calls:
            result=call.get()
            print('scored',fold,result['part'],result['pairs'],flush=True)
    report=evaluate.remote()
    Path('reports/m017_evaluation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'baseline':report['baseline'],'selected':report['selected']},indent=2),flush=True)
