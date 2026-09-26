"""D017: full-inventory reverse-owner competition, bounded cloud diagnostic."""
import json
import shutil
from pathlib import Path

import modal
from modal_app import image, volume, VOLUME_ROOT, SCRATCH

base_image = image.add_local_python_source('modal_app')
gpu_image = (modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent / 'requirements.txt'))
    .pip_install('torch==2.8.0', 'transformers==4.57.1',
                 'huggingface_hub==0.36.0', 'sentencepiece==0.2.1')
    .env({'PYTHONPATH': '/app/src'})
    .add_local_dir(str(Path(__file__).parent / 'src'), '/app/src')
    .add_local_python_source('modal_app'))

app = modal.App('team517-d017-ownership')
ROOT = VOLUME_ROOT / 'project/experiments/d017'


@app.function(image=base_image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, timeout=1800)
def prepare(fold: str = 'calibrate'):
    from ber.ownership import prepare as build
    out = ROOT / fold
    if (out/'prepare.json').exists():
        return json.loads((out/'prepare.json').read_text())
    db = SCRATCH / 'artifacts/ownership.duckdb'
    db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VOLUME_ROOT/'project/artifacts/data_v3.duckdb', db)
    result = build(db, VOLUME_ROOT/'project/experiments/int003/depth10', out, fold)
    volume.commit()
    return result


@app.function(image=gpu_image, volumes={str(VOLUME_ROOT): volume}, cpu=4,
              memory=24576, gpu='L4', timeout=1800)
def evaluate(fold: str = 'calibrate'):
    from ber.ownership import evaluate_owners
    encoder = VOLUME_ROOT/'project/experiments/int005/encoder'
    if not (encoder/'training_report.json').exists():
        raise ValueError('Encoder training has not finished')
    result = evaluate_owners(ROOT/fold, encoder)
    volume.commit()
    return result


@app.local_entrypoint()
def main(fold: str = 'calibrate'):
    print(json.dumps(prepare.remote(fold)), flush=True)
    report = evaluate.remote(fold)
    Path(f'reports/d017_{fold}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
