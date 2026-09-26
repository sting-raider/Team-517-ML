"""Full-pool, capped-neural blocker plus multilingual reranker evaluation."""
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
app=modal.App('team517-int005-m017-capped-match')
ROOT=VOLUME_ROOT/'project/experiments/capped_match'
RETRIEVAL=VOLUME_ROOT/'project/experiments/int005_retrieval'
BASE=VOLUME_ROOT/'project/experiments/int003/depth10'
CROSS=VOLUME_ROOT/'project/experiments/m017'


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=12288,gpu='L4',timeout=900)
def score(country:str,prefix:str,scheme:str='capped'):
    from ber.capped_match import score_dense_only
    score_root=ROOT if scheme=='capped' else ROOT/scheme
    result=score_dense_only(VOLUME_ROOT/'project/artifacts/data_v3.duckdb',
                            RETRIEVAL/country/f'{scheme}_{prefix}_pairs.jsonl',
                            CROSS/'model',score_root/f'{country}_{prefix}.npz')
    volume.commit()
    return result


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=16384,timeout=900)
def evaluate(scheme:str='capped'):
    from ber.capped_match import evaluate_capped_match
    score_root=ROOT if scheme=='capped' else ROOT/scheme
    result=evaluate_capped_match(BASE,RETRIEVAL,CROSS/'scores',score_root,
                                 score_root/'evaluation.json',scheme)
    volume.commit()
    return result


@app.local_entrypoint()
def main(scheme:str='capped',action:str='run'):
    if scheme not in ('capped','compact'):
        raise ValueError('Expected capped or compact')
    if action not in ('run','evaluate'):
        raise ValueError('Expected run or evaluate')
    if action=='run':
        calls=[score.spawn(country,prefix,scheme) for country in ('India','US')
               for prefix in ('cal','hold')]
        for call in calls:
            value=call.get()
            print('dense-only score',value['pairs'],value['country_fold'],flush=True)
    result=evaluate.remote(scheme)
    Path(f'reports/{scheme}_match_evaluation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'pairs':result['pairs'],'dense_only_pairs':result['dense_only_pairs'],
                      'selected':result['selected']},indent=2),flush=True)
