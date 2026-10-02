"""M018: train the same permitted reranker on all labeled positive fragments."""
import json
from pathlib import Path

import modal
from modal_app import volume,VOLUME_ROOT

image=(modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent/'requirements.txt'))
    .pip_install('torch==2.8.0','transformers==4.57.1',
                 'huggingface_hub==0.36.0','sentencepiece==0.2.1')
    .env({'PYTHONPATH':'/app/src'})
    .add_local_dir(str(Path(__file__).parent/'src'),'/app/src')
    .add_local_python_source('modal_app'))
app=modal.App('team517-m018-all-positive-reranker')
ROOT=VOLUME_ROOT/'project/experiments/m018'


@app.function(image=image,volumes={str(VOLUME_ROOT):volume},cpu=4,
              memory=24576,gpu='L4',timeout=3600)
def fit():
    from ber.crossencoder import train
    report=train(VOLUME_ROOT/'project/experiments/int005/data',ROOT/'model',
                 max_seconds=3300,callback=volume.commit,positive_limit=None)
    volume.commit()
    return report


@app.local_entrypoint()
def main():
    report=fit.remote()
    Path('reports/m018_training.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
