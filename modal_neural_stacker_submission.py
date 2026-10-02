"""End-to-end stacked CatBoost matching on the exact frozen neural32 pool."""
import gzip
import json
import shutil
from pathlib import Path

import modal
from modal_app import image,volume,VOLUME_ROOT,SCRATCH

base_image=image.add_local_python_source('modal_app')
gpu_image=(modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent/'requirements.txt'))
    .pip_install('torch==2.8.0','transformers==4.57.1',
                 'huggingface_hub==0.36.0','sentencepiece==0.2.1','faiss-cpu==1.12.0')
    .env({'PYTHONPATH':'/app/src'})
    .add_local_dir(str(Path(__file__).parent/'src'),'/app/src')
    .add_local_python_source('modal_app'))
app=modal.App('team517-neural32-stacker-test-submission')
RUN='submission_v14_stacker'
STACKER=VOLUME_ROOT/'project/experiments/stacker/stacker_final.cbm'
COUNTRIES=('France','India','US')


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},cpu=8,
              memory=32768,gpu='L4',timeout=14400)
def score(country:str,part:int,parts_per_country:int,threshold:float,dense_prior:float):
    from ber.predict_neural import score_partition
    if country not in COUNTRIES:
        raise ValueError('Invalid country')
    global_part=COUNTRIES.index(country)*parts_per_country+part
    all_parts=len(COUNTRIES)*parts_per_country
    local_db=SCRATCH/'artifacts/neural_test.duckdb'
    local_db.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(VOLUME_ROOT/'project/artifacts/data_v3.duckdb',local_db)
    out=VOLUME_ROOT/'project/output'/f'{RUN}_part{global_part}of{all_parts}'
    result=score_partition(local_db,
        VOLUME_ROOT/'project/experiments/int005_test_retrieval',
        VOLUME_ROOT/'project/experiments/int005/encoder',
        VOLUME_ROOT/'project/experiments/m017/model',
        out,country,part,parts_per_country,threshold,
        batch_size=5000,checkpoint=volume.commit,
        cat_path=VOLUME_ROOT/'project/experiments/int003/depth10/mixed.cbm',
        dense_prior=dense_prior,stacker_path=STACKER)
    original=VOLUME_ROOT/'project/output'/f'submission_v5_neural32_part{global_part}of{all_parts}'
    expected=json.loads((original/'completion.json').read_text())
    if result['candidate_sha256']!=expected['candidate_sha256']:
        raise ValueError('Stacker rerun changed frozen candidate pool')
    volume.commit()
    return result


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},cpu=8,
              memory=32768,gpu='L4',timeout=1200)
def probe(threshold:float,dense_prior:float):
    from ber.predict_neural import score_partition
    local_db=SCRATCH/'artifacts/neural_probe.duckdb'
    local_db.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(VOLUME_ROOT/'project/artifacts/data_v3.duckdb',local_db)
    out=VOLUME_ROOT/'project/experiments/neural_probe_stacker'
    result=score_partition(local_db,
        VOLUME_ROOT/'project/experiments/int005_test_retrieval',
        VOLUME_ROOT/'project/experiments/int005/encoder',
        VOLUME_ROOT/'project/experiments/m017/model',
        out,'France',0,4,threshold,batch_size=100,anchor_limit=100,
        checkpoint=volume.commit,
        cat_path=VOLUME_ROOT/'project/experiments/int003/depth10/mixed.cbm',
        dense_prior=dense_prior,stacker_path=STACKER)
    volume.commit()
    return result


@app.function(image=base_image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=16384,timeout=3600)
def merge(partitions:int):
    from modal_app import merge_score
    return merge_score.local(RUN,partitions,32)


@app.function(image=base_image,volumes={str(VOLUME_ROOT):volume},cpu=2,
              memory=4096,timeout=900)
def compress_matching():
    from ber.predict import sha256
    out=VOLUME_ROOT/'project/output'/RUN
    receipt=json.loads((out/'completion.json').read_text())
    source=out/'matching_results.tsv'
    if sha256(source)!=receipt['matching_sha256']:
        raise ValueError('Validated matching checksum mismatch')
    target=out/'matching_results.tsv.gz'
    with source.open('rb') as src,target.open('wb') as dst:
        with gzip.GzipFile(filename='',mode='wb',fileobj=dst,compresslevel=3,mtime=0) as gz:
            shutil.copyfileobj(src,gz,1<<20)
    result={'matching_sha256':receipt['matching_sha256'],
            'candidate_sha256':receipt['candidate_sha256'],
            'compressed_sha256':sha256(target),
            'compressed_bytes':target.stat().st_size}
    (out/'package.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    volume.commit()
    return result


@app.local_entrypoint()
def main(threshold:float=.8,dense_prior:float=-2.,parts_per_country:int=4,
         action:str='probe',country:str='France',part:int=0):
    if parts_per_country not in (2,4,8):
        raise ValueError('Choose 2, 4, or 8 partitions per country')
    if action=='probe':
        print(json.dumps(probe.remote(threshold,dense_prior),indent=2),flush=True)
        return
    if action=='one':
        print(json.dumps(score.remote(country,part,parts_per_country,threshold,dense_prior),
                         indent=2),flush=True)
        return
    if action!='run':
        raise ValueError('Expected run, one, or probe')
    calls=[score.spawn(country,part,parts_per_country,threshold,dense_prior)
           for country in COUNTRIES for part in range(parts_per_country)]
    for call in calls:
        result=call.get()
        print('completed',result['country'],result['partition'],result['anchors'],flush=True)
    completed=merge.remote(len(COUNTRIES)*parts_per_country)
    packaged=compress_matching.remote()
    report={'threshold':threshold,'dense_prior':dense_prior,
            'parts_per_country':parts_per_country,
            'completion':completed,'package':packaged}
    Path('reports/neural32_submission.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
