"""Build full test target ANN indexes for INT005, country and hash sharded."""
import json
from pathlib import Path

import modal
from modal_app import volume,VOLUME_ROOT

ROOT=VOLUME_ROOT/'project/experiments/int005_test_retrieval'
DB=VOLUME_ROOT/'project/artifacts/data_v3.duckdb'
ENCODER=VOLUME_ROOT/'project/experiments/int005/encoder'
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
app=modal.App('team517-int005-test-ann')


def folder(country,part):
    return ROOT/country/f'part{part}'


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=16384,gpu='L4',timeout=1500)
def encode(country:str,part:int):
    from ber.dense_retrieval import encode_target_shard
    out=folder(country,part)
    if (out/'encoded.json').exists():
        receipt=json.loads((out/'encoded.json').read_text())
        if receipt.get('split')!='test':
            raise ValueError('Stale non-test vectors')
        return receipt
    result=encode_target_shard(DB,ENCODER,out,country,part,split='test')
    volume.commit()
    return result


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},cpu=8,
              memory=16384,timeout=1500)
def index(country:str,part:int):
    from ber.dense_retrieval import build_index
    out=folder(country,part)
    if (out/'indexed.json').exists():
        receipt=json.loads((out/'indexed.json').read_text())
        if receipt.get('split')!='test':
            raise ValueError('Stale non-test index')
        return receipt
    result=build_index(out)
    volume.commit()
    return result


@app.local_entrypoint()
def main(action:str='index'):
    if action!='index':
        raise ValueError('Expected index')
    targets=[(country,part) for country in ('France','India','US') for part in range(4)]
    for label,func in [('encode',encode),('index',index)]:
        calls=[func.spawn(country,part) for country,part in targets]
        for call in calls:
            result=call.get()
            print(label,result['country'],result['part'],result['vectors'],flush=True)
    summary={'countries':['France','India','US'],'shards':len(targets),
             'protocol':'Complete test S2/S3 inventory; country partitioned IVF2048-SQ8; MIT INT005 encoder'}
    Path('reports/int005_test_index.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)
