"""D017 conflict-only test export; no raw records or TSV outputs enter Git."""
import json
from pathlib import Path

import modal
from modal_app import image, volume, VOLUME_ROOT

base_image = image.add_local_python_source('modal_app')
gpu_image = (modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent/'requirements.txt'))
    .pip_install('torch==2.8.0','transformers==4.57.1',
                 'huggingface_hub==0.36.0','sentencepiece==0.2.1')
    .env({'PYTHONPATH':'/app/src'})
    .add_local_dir(str(Path(__file__).parent/'src'),'/app/src')
    .add_local_python_source('modal_app'))
app = modal.App('team517-d017-test-conflicts')
ROOT = VOLUME_ROOT/'project/experiments/d017/test_conflicts'
BASE = VOLUME_ROOT/'project/output/submission_v3_d10/matching_results.tsv'
OUT = VOLUME_ROOT/'project/output/submission_v4_d017_conflicts'


@app.function(image=base_image,volumes={str(VOLUME_ROOT):volume},cpu=8,memory=32768,timeout=900)
def prepare():
    from ber.conflict_filter import prepare as build
    result=build(VOLUME_ROOT/'project/artifacts/data_v3.duckdb',BASE,ROOT)
    volume.commit()
    return result


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=24576,gpu='L4',timeout=900)
def score():
    from ber.conflict_filter import score as predict
    result=predict(ROOT,VOLUME_ROOT/'project/experiments/int005/encoder',.05)
    volume.commit()
    return result


@app.function(image=base_image,volumes={str(VOLUME_ROOT):volume},cpu=4,memory=8192,timeout=600)
def export():
    from ber.conflict_filter import write_submission
    result=write_submission(BASE,ROOT/'removed.parquet',OUT)
    volume.commit()
    return result


@app.local_entrypoint()
def main():
    print(json.dumps(prepare.remote()),flush=True)
    print(json.dumps(score.remote()),flush=True)
    result=export.remote()
    Path('reports/d017_test_conflicts.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
