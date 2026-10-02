"""Bounded cross-encoder reranking experiment for reverse owner competition."""
import json
from pathlib import Path

import modal

from modal_app import volume,VOLUME_ROOT

gpu_image=(modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent/'requirements.txt'))
    .pip_install('torch==2.8.0','transformers==4.57.1',
                 'huggingface_hub==0.36.0','sentencepiece==0.2.1')
    .env({'PYTHONPATH':'/app/src'})
    .add_local_dir(str(Path(__file__).parent/'src'),'/app/src')
    .add_local_python_source('modal_app'))
cpu_image=(modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent/'requirements.txt'))
    .env({'PYTHONPATH':'/app/src'})
    .add_local_dir(str(Path(__file__).parent/'src'),'/app/src')
    .add_local_python_source('modal_app'))

app=modal.App('team517-owner-cross-diagnostic')
ROOT=VOLUME_ROOT/'project/experiments/owner_cross'
D017=VOLUME_ROOT/'project/experiments/d017'


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},
              cpu=4,memory=24576,gpu='L4',timeout=1800)
def score(fold:str):
    from ber.owner_cross import score_fold
    if fold not in ('calibrate','holdout'):
        raise ValueError('Invalid fold')
    result=score_fold(D017/fold,VOLUME_ROOT/'project/experiments/m017/model',
                      ROOT/f'{fold}.npz')
    volume.commit()
    return result


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},
              cpu=4,memory=8192,timeout=600)
def evaluate():
    from ber.owner_cross import evaluate_folds
    result=evaluate_folds(D017,ROOT,ROOT/'evaluation.json')
    volume.commit()
    return result


@app.local_entrypoint()
def main(action:str='run'):
    if action not in ('run','evaluate'):
        raise ValueError('Expected run or evaluate')
    if action=='run':
        calls=[score.spawn(fold) for fold in ('calibrate','holdout')]
        for call in calls:
            print('scored',json.dumps(call.get()),flush=True)
    report=evaluate.remote()
    Path('reports/owner_cross_evaluation.json').write_text(
        json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'baseline':{f:report['folds'][f]['baseline']
                                   for f in ('calibrate','holdout')},
                      'selected_margin':report['selected_margin'],
                      'selected_calibration':report['folds']['calibrate']['variants'][report['selected_margin']],
                      'selected_holdout':report['folds']['holdout']['variants'][report['selected_margin']]},
                     indent=2),flush=True)
