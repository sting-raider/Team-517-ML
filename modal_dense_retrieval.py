"""INT005 full-inventory country-sharded ANN retrieval measurement."""
import json
import shutil
from pathlib import Path

import modal
from modal_app import volume,VOLUME_ROOT,SCRATCH

ROOT=VOLUME_ROOT/'project/experiments/int005_retrieval'
DB=VOLUME_ROOT/'project/artifacts/data_v3.duckdb'
ENCODER=VOLUME_ROOT/'project/experiments/int005/encoder'
FEATURES=VOLUME_ROOT/'project/experiments/int003/depth10'
gpu_image=(modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent/'requirements.txt'))
    .pip_install('torch==2.8.0','transformers==4.57.1',
                 'huggingface_hub==0.36.0','sentencepiece==0.2.1','faiss-cpu==1.12.0')
    .env({'PYTHONPATH':'/app/src'})
    .add_local_dir(str(Path(__file__).parent/'src'),'/app/src')
    .add_local_python_source('modal_app'))
cpu_image=(modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent/'requirements.txt'))
    .pip_install('faiss-cpu==1.12.0')
    .env({'PYTHONPATH':'/app/src'})
    .add_local_dir(str(Path(__file__).parent/'src'),'/app/src')
    .add_local_python_source('modal_app'))
app=modal.App('team517-int005-full-inventory-ann')


def folder(country,part):
    return ROOT/country/f'part{part}'


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=16384,gpu='L4',timeout=1500)
def encode(country:str,part:int):
    from ber.dense_retrieval import encode_target_shard
    out=folder(country,part)
    if (out/'encoded.json').exists():
        return json.loads((out/'encoded.json').read_text())
    result=encode_target_shard(DB,ENCODER,out,country,part)
    volume.commit()
    return result


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},cpu=8,
              memory=16384,timeout=1500)
def index(country:str,part:int):
    from ber.dense_retrieval import build_index
    out=folder(country,part)
    if (out/'indexed.json').exists():
        return json.loads((out/'indexed.json').read_text())
    result=build_index(out)
    volume.commit()
    return result


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},cpu=8,
              memory=16384,gpu='L4',timeout=900)
def search(country:str,part:int,fold:str='calibrate'):
    from ber.dense_retrieval import search_calibration
    out=folder(country,part)
    result=search_calibration(DB,ENCODER,out,FEATURES,country,fold=fold)
    volume.commit()
    return result


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=8192,timeout=600)
def evaluate(country:str):
    from ber.dense_retrieval import evaluate_search
    paths=[folder(country,p)/'cal_nprobe64.npz' for p in range(4)]
    result=evaluate_search(DB,FEATURES,paths,country)
    (ROOT/country/'evaluation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    volume.commit()
    return result


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},cpu=8,
              memory=32768,timeout=1200)
def capped(country:str,fold:str='calibrate',base_cap:int=160):
    from ber.dense_retrieval import evaluate_capped
    local=SCRATCH/'artifacts/dense_cap.duckdb'
    local.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(DB,local)
    prefix='cal' if fold=='calibrate' else 'hold'
    paths=[folder(country,p)/f'{prefix}_nprobe64.npz' for p in range(4)]
    stem='compact' if base_cap==32 else 'capped'
    result=evaluate_capped(local,FEATURES,paths,country,fold=fold,base_cap=base_cap,
                           output_pairs=ROOT/country/f'{stem}_{prefix}_pairs.jsonl')
    (ROOT/country/f'{stem}_{prefix}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    volume.commit()
    return result


@app.local_entrypoint()
def main(country:str='India',action:str='run'):
    if country not in ('India','US'):
        raise ValueError('Calibration labels exist only for India and US')
    if action not in ('run','evaluate','capped','holdout','compact','compact_holdout'):
        raise ValueError('Expected run, evaluate, capped, holdout, or compact')
    if action=='run':
        for phase,function in [('encode',encode),('index',index),('search',search)]:
            calls=[function.spawn(country,p) for p in range(4)]
            for call in calls:
                result=call.get()
                print(phase,json.dumps({k:result[k] for k in ('country','part') if k in result}),flush=True)
    if action=='holdout':
        calls=[search.spawn(country,p,'holdout') for p in range(4)]
        for call in calls:
            result=call.get()
            print('search holdout',result['part'],flush=True)
    if action=='compact_holdout':
        result=capped.remote(country,'holdout',32)
    elif action=='compact':
        result=capped.remote(country,'calibrate',32)
    elif action=='holdout':
        result=capped.remote(country,'holdout')
    elif action=='capped':
        result=capped.remote(country)
    else:
        result=evaluate.remote(country)
    suffix=action if action!='run' else 'ann'
    Path(f'reports/int005_{suffix}_{country.lower()}.json').write_text(
        json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)
