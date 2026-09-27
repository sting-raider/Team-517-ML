"""CPU-only exact-name/blank-address recovery on the frozen v5 candidates."""
import json
import gzip
import shutil
from pathlib import Path

import modal
from modal_app import volume,VOLUME_ROOT

cpu_image=(modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent/'requirements.txt'))
    .env({'PYTHONPATH':'/app/src'})
    .add_local_dir(str(Path(__file__).parent/'src'),'/app/src')
    .add_local_python_source('modal_app'))
app=modal.App('team517-v6-blank-address-recovery')


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},
              cpu=4,memory=16384,timeout=3600)
def run():
    from ber.predict import sha256
    from ber.recover_blank import recover

    source=VOLUME_ROOT/'project/output/submission_v5_neural32'
    dest=VOLUME_ROOT/'project/output/submission_v6_blank_recovery'
    dest.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((source/'completion.json').read_text())
    if receipt['status']!='PASS' or \
            sha256(source/'candidate_pairs.tsv')!=receipt['candidate_sha256'] or \
            sha256(source/'matching_results.tsv')!=receipt['matching_sha256']:
        raise ValueError('Frozen v5 source checksums disagree')
    result=recover(VOLUME_ROOT/'project/artifacts/data_v3.duckdb',
                   source/'candidate_pairs.tsv',source/'matching_results.tsv',
                   dest/'matching_results.tsv')
    result['matching_sha256']=sha256(dest/'matching_results.tsv')
    result['candidate_sha256']=receipt['candidate_sha256']
    result['candidate_cap']=32
    result['protocol']='Unique Source-1 normalized name within country; candidate target has identical normalized name and empty normalized address; add only from exact v5 candidate file'
    (dest/'completion.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    volume.commit()
    return result


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},
              cpu=2,memory=4096,timeout=900)
def compress():
    from ber.predict import sha256
    dest=VOLUME_ROOT/'project/output/submission_v6_blank_recovery'
    receipt=json.loads((dest/'completion.json').read_text())
    source=dest/'matching_results.tsv'
    if sha256(source)!=receipt['matching_sha256']:
        raise ValueError('Recovery output checksum changed')
    target=dest/'matching_results.tsv.gz'
    with source.open('rb') as src,target.open('wb') as dst:
        with gzip.GzipFile(filename='',mode='wb',fileobj=dst,
                           compresslevel=3,mtime=0) as gz:
            shutil.copyfileobj(src,gz,1<<20)
    volume.commit()
    return {'compressed_bytes':target.stat().st_size,
            'compressed_sha256':sha256(target),
            'matching_sha256':receipt['matching_sha256']}


@app.function(image=cpu_image,volumes={str(VOLUME_ROOT):volume},
              cpu=2,memory=4096,timeout=1800)
def compress_candidates():
    from ber.predict import sha256
    source_dir=VOLUME_ROOT/'project/output/submission_v5_neural32'
    receipt=json.loads((source_dir/'completion.json').read_text())
    source=source_dir/'candidate_pairs.tsv'
    if sha256(source)!=receipt['candidate_sha256']:
        raise ValueError('Frozen candidate checksum changed')
    target=source_dir/'candidate_pairs.tsv.gz'
    with source.open('rb') as src,target.open('wb') as dst:
        with gzip.GzipFile(filename='',mode='wb',fileobj=dst,
                           compresslevel=3,mtime=0) as gz:
            shutil.copyfileobj(src,gz,1<<20)
    volume.commit()
    return {'compressed_bytes':target.stat().st_size,
            'compressed_sha256':sha256(target),
            'candidate_sha256':receipt['candidate_sha256']}


@app.local_entrypoint()
def main(action:str='run'):
    if action=='run':
        result=run.remote()
        Path('reports/blank_recovery_submission.json').write_text(
            json.dumps(result,indent=2),encoding='utf-8')
    elif action=='compress':
        result=compress.remote()
    elif action=='compress-candidates':
        result=compress_candidates.remote()
    else:
        raise ValueError('Expected run, compress, or compress-candidates')
    print(json.dumps(result,indent=2),flush=True)
