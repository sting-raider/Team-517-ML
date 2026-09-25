"""Download the audited pretrained initialization; never fetch business records."""
import json
from pathlib import Path
from huggingface_hub import HfApi,snapshot_download


def main():
    manifest=json.loads(Path('reports/pretrained_model.json').read_text())
    info=HfApi().model_info(manifest['model'],revision=manifest['revision'])
    if info.card_data.get('license')!=manifest['license'] or manifest['license'] not in ('mit','apache-2.0'):
        raise ValueError('Checkpoint license does not match the audited manifest')
    snapshot_download(repo_id=manifest['model'],revision=manifest['revision'],
        local_dir='artifacts/pretrained/multilingual-e5-small',
        allow_patterns=['model.safetensors','config.json','tokenizer.json','tokenizer_config.json',
                        'sentencepiece.bpe.model','special_tokens_map.json','README.md'])


if __name__=='__main__':
    main()
