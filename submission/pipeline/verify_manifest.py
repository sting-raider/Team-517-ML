"""Check saved checkpoint integrity without loading models or using cloud compute."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_models(root):
    manifest = json.loads((root / 'reproduction_manifest.json').read_text(encoding='utf-8'))
    for item in manifest['model_files']:
        path = root / item['path']
        if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError(f'Checkpoint integrity failure: {path}')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outputs', type=Path,
                        help='Optionally verify the original organizer-test output files')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    manifest = verify_models(root)
    if args.outputs:
        for name, expected in manifest['outputs'].items():
            if digest(args.outputs / name) != expected:
                raise ValueError(f'Submitted output checksum mismatch: {name}')
    print('PASS: selected V13 checkpoint integrity' + (' and output identity' if args.outputs else ''))


if __name__ == '__main__':
    main()
