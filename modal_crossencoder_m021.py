"""M021: test a larger licensed multilingual reranker on supplied labels."""
import json
from pathlib import Path

import modal
from modal_app import volume, VOLUME_ROOT


image = (modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent / 'requirements.txt'))
    .pip_install('torch==2.8.0', 'transformers==4.57.1',
                 'huggingface_hub==0.36.0', 'sentencepiece==0.2.1')
    .env({'PYTHONPATH': '/app/src'})
    .add_local_dir(str(Path(__file__).parent / 'src'), '/app/src')
    .add_local_python_source('modal_app'))

app = modal.App('team517-m021-bge-reranker')
ROOT = VOLUME_ROOT / 'project/experiments/m021'
MODEL = 'BAAI/bge-reranker-v2-m3'
REVISION = '953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e'


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, gpu='A100-40GB', timeout=8100)
def fit():
    from ber.crossencoder import train

    report = train(VOLUME_ROOT / 'project/experiments/int005/data',
                   ROOT / 'model', max_seconds=7500, callback=volume.commit,
                   positive_limit=None, model_name=MODEL, revision=REVISION,
                   batch_size=16, learning_rate=1e-5,
                   checkpoint_steps=5000)
    volume.commit()
    return report


@app.local_entrypoint()
def main():
    report = fit.remote()
    Path('reports/m021_training.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
