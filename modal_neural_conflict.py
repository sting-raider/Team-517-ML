"""Optional D017 owner-conflict postprocessor for the exact neural32 submission."""
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

app = modal.App('team517-neural32-conflict-alternative')
ROOT = VOLUME_ROOT/'project/experiments/d017/neural32_conflicts'
BASE = VOLUME_ROOT/'project/output/submission_v5_neural32/matching_results.tsv'
OUT = VOLUME_ROOT/'project/output/submission_v6_neural32_owner'


@app.function(image=base_image,volumes={str(VOLUME_ROOT):volume},
              cpu=8,memory=32768,timeout=1200)
def prepare():
    from ber.conflict_filter import prepare as build
    if not (BASE.parent/'completion.json').exists():
        raise FileNotFoundError('Validated neural32 source output is not complete')
    result=build(VOLUME_ROOT/'project/artifacts/data_v3.duckdb',BASE,ROOT)
    volume.commit()
    return result


@app.function(image=gpu_image,volumes={str(VOLUME_ROOT):volume},
              cpu=4,memory=24576,gpu='L4',timeout=1200)
def score(margin:float):
    from ber.conflict_filter import score as predict
    result=predict(ROOT,VOLUME_ROOT/'project/experiments/int005/encoder',margin)
    volume.commit()
    return result


@app.function(image=base_image,volumes={str(VOLUME_ROOT):volume},
              cpu=4,memory=8192,timeout=900)
def export():
    from ber.conflict_filter import write_submission
    result=write_submission(BASE,ROOT/'removed.parquet',OUT)
    volume.commit()
    return result


@app.local_entrypoint()
def main(margin:float=.05):
    if not 0<=margin<=.2:
        raise ValueError('Margin must be within 0..0.2')
    prepared=prepare.remote()
    scored=score.remote(margin)
    exported=export.remote()
    report={'input_run':'submission_v5_neural32',
            'output_run':'submission_v6_neural32_owner',
            'candidate_run':'submission_v5_neural32',
            'protocol':'Remove only lower-scoring duplicate owner claims; reuse exact neural32 candidate TSV',
            'prepare':prepared,'score':scored,'export':exported}
    Path('reports/neural32_conflict_alternative.json').write_text(
        json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
