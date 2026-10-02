"""Stage supplied TSVs and the exact packaged V13 checkpoints to a fresh volume."""
import argparse
import json
import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True,
                        help='Organizer dataset folder containing train/ and test/')
    args = parser.parse_args()
    from pipeline.verify_manifest import verify_models
    verify_models(ROOT)
    files = []
    for split in ('train', 'test'):
        for source in (1, 2, 3):
            name = f'{split}_source{source}.tsv'
            files.append((args.dataset / split / name, f'/dataset/{split}/{name}'))
    files.append((args.dataset / 'train/train_ground_truth.tsv',
                  '/dataset/train/train_ground_truth.tsv'))
    destinations = {'int003': '/project/experiments/int003/depth10',
                    'encoder': '/project/experiments/int005/encoder',
                    'crossencoder': '/project/experiments/m017/model'}
    for folder, remote in destinations.items():
        for path in sorted((ROOT / 'models' / folder).rglob('*')):
            if path.is_file():
                files.append((path, f'{remote}/{path.relative_to(ROOT / "models" / folder).as_posix()}'))
    for path, _ in files:
        if not path.is_file():
            raise FileNotFoundError(path)
    name = os.environ.get('TEAM517_MODAL_VOLUME', 'team517-v13-reproduction')
    volume = modal.Volume.from_name(name, create_if_missing=True)
    with volume.batch_upload(force=True) as upload:
        for local, remote in files:
            upload.put_file(str(local), remote)
    (ROOT / 'reports').mkdir(exist_ok=True)
    print(json.dumps({'volume': name, 'staged_files': len(files)}, indent=2))


if __name__ == '__main__':
    main()
