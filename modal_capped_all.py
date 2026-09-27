"""Evaluate M018 on exactly the same frozen 32-candidate development pool as V5."""
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
app=modal.App('team517-m018-capped-evaluation')
ROOT=VOLUME_ROOT/'project/experiments/m018'
RETRIEVAL=VOLUME_ROOT/'project/experiments/int005_retrieval'
BASE=VOLUME_ROOT/'project/experiments/int003/depth10'
M017=VOLUME_ROOT/'project/experiments/m017'


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=12288,gpu='L4',timeout=1500)
def score(country:str,prefix:str):
    from ber.capped_match import score_dense_only
    result=score_dense_only(VOLUME_ROOT/'project/artifacts/data_v3.duckdb',
        RETRIEVAL/country/f'capped_{prefix}_pairs.jsonl',
        ROOT/'model',ROOT/'capped_scores'/f'{country}_{prefix}.npz',
        dense_only=False)
    volume.commit()
    return result


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=8192,timeout=900)
def evaluate():
    from ber.capped_match import evaluate_capped_match
    result=evaluate_capped_match(BASE,RETRIEVAL,M017/'scores',
        VOLUME_ROOT/'project/experiments/capped_match',
        ROOT/'capped_evaluation.json',override_cross_root=ROOT/'capped_scores')
    volume.commit()
    return result


@app.local_entrypoint()
def main():
    calls=[score.spawn(country,prefix) for country in ('India','US')
           for prefix in ('cal','hold')]
    for call in calls:
        result=call.get()
        print('M018 scored',result['pairs'],result['country_fold'],flush=True)
    result=evaluate.remote()
    Path('reports/m018_capped_evaluation.json').write_text(
        json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'selected':result['selected'],
                      'error_budget':result['error_budget']},indent=2),flush=True)
