"""Build the required V13 ZIP with exact outputs, checkpoints, and runnable source."""
import argparse
import ast
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCH_SHA = '2d4ca5400f2e87daf886c5f4c8e1c0769720a2dd889dfd9e2de149f848199e3a'
CAND_SHA = 'fa286e237b9bdd31905f901d2a1449771698249d4c1dfe45dcbfa38bf647c3ec'
CORE_MODAL = ('modal_app.py', 'modal_v2.py', 'modal_v3.py', 'modal_dense.py',
              'modal_crossencoder.py', 'modal_dense_retrieval.py', 'modal_dense_test.py',
              'modal_neural_submission.py', 'modal_recover_blank.py')
REPORTS = ('reports/int005_training.json', 'reports/m017_training.json',
           'reports/capped_match_evaluation.json', 'reports/neural32_submission.json',
           'reports/blank_recovery_submission.json', 'reports/m020_owner_label_gate.json',
           'reports/SUBMISSIONS.json', 'reports/FINAL_V13_PACKAGE_VALIDATION.json')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relocate(source):
    """Adapt original Modal entrypoints to the required src/pipeline layout."""
    source = source.replace('from modal_app import ', 'from pipeline.modal_app import ')
    source = source.replace("add_local_python_source('modal_app')", "add_local_python_source('pipeline.modal_app')")
    source = source.replace('Path(__file__).parent', 'Path(__file__).resolve().parents[2]')
    source = source.replace('ROOT / "tests"', 'ROOT / "src" / "tests"')
    source = source.replace('VOLUME_NAME = "team517-business-er"',
                            'VOLUME_NAME = os.environ.get("TEAM517_MODAL_VOLUME", "team517-v13-reproduction")')
    source = source.replace('.env({', '.env({"TEAM517_MODAL_VOLUME": os.environ.get("TEAM517_MODAL_VOLUME", "team517-v13-reproduction"), ')
    source = 'import os\n' + source
    ast.parse(source)
    return source


def stage_bundle(stage, model_root):
    code = stage / 'code/business_entity_resolution'
    code.mkdir(parents=True, exist_ok=False)
    for name in ('README.md', 'requirements.txt', 'requirements-gpu.txt', 'MODEL_LICENSES.md', 'LICENSE'):
        shutil.copy2(ROOT / 'submission' / name, code / name)
    project = (ROOT / 'pyproject.toml').read_text(encoding='utf-8').replace('setuptools>=68', 'setuptools==68.2.2')
    (code / 'pyproject.toml').write_text(project, encoding='utf-8')
    for path in (ROOT / 'src').rglob('*'):
        if path.is_file() and path.suffix in ('.py', '.cpp', '.h'):
            target = code / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    pipeline = code / 'src/pipeline'
    pipeline.mkdir(exist_ok=True)
    (pipeline / '__init__.py').write_text('', encoding='utf-8')
    for name in CORE_MODAL:
        (pipeline / name).write_text(relocate((ROOT / name).read_text(encoding='utf-8')), encoding='utf-8')
    for path in (ROOT / 'submission/pipeline').glob('*.py'):
        shutil.copy2(path, pipeline / path.name)
    shutil.copy2(ROOT / 'tools/resolve_owner_submission.py', pipeline / 'resolve_owner_submission.py')
    stage_source = (ROOT / 'tools/stage_modal.py').read_text(encoding='utf-8')
    stage_source = stage_source.replace('.parents[1]', '.parents[2]').replace('VOLUME_NAME = "team517-business-er"',
        'VOLUME_NAME = os.environ.get("TEAM517_MODAL_VOLUME", "team517-v13-reproduction")')
    (pipeline / 'stage_modal.py').write_text('import os\n' + stage_source, encoding='utf-8')
    for path in (ROOT / 'tests').glob('*.py'):
        target = code / 'src/tests' / path.name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(path, target)
    for name in REPORTS:
        target = code / name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(ROOT / name, target)
    shutil.copy2(ROOT / 'output/submission_v13_owner_country/owner_resolution.json', code / 'reports/v13_owner_resolution.json')
    for folder in ('encoder', 'crossencoder'):
        destination = code / 'models' / folder
        destination.mkdir(parents=True)
        for name in ('config.json', 'model.safetensors', 'tokenizer.json', 'tokenizer_config.json',
                     'special_tokens_map.json', 'sentencepiece.bpe.model', 'training_report.json'):
            shutil.copy2(model_root / folder / name, destination / name)
    destination = code / 'models/int003'
    destination.mkdir()
    for name in ('mixed.cbm', 'model_config.json', 'report.json'):
        shutil.copy2(ROOT / 'artifacts/model_backups/int003/depth10' / name, destination / name)
    for path in (ROOT / 'submission/licenses').glob('*'):
        destination = code / 'licenses' / path.name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(path, destination)
    manifest = {'selected_version': 'v13-country-owner', 'public_score': .969,
                'score_evidence': 'Team-reported leaderboard result, 2026-10-02',
                'outputs': {'matching_results.tsv': MATCH_SHA, 'candidate_pairs.tsv': CAND_SHA},
                'inference': {'threshold': .95, 'dense_prior': -2., 'candidate_cap': 32,
                              'dense_slots': 16, 'base_cap': 160, 'nprobe': 64,
                              'target_shards_per_country': 4, 'scoring_parts_per_country': 4},
                'owner_gates': {'India': [50, 5], 'US': [20, 2], 'France': [20, 2]},
                'model_files': []}
    for path in sorted((code / 'models').rglob('*')):
        if path.is_file():
            manifest['model_files'].append({'path': path.relative_to(code).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)})
    (code / 'reproduction_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    shutil.copy2(ROOT / 'Documentation_template.md', stage / 'Documentation_template.md')
    for path in (code / 'src').rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    return code


def package(matching, candidate, output, model_root, stage, reuse_stage=False):
    for path, expected in ((matching, MATCH_SHA), (candidate, CAND_SHA)):
        if digest(path) != expected:
            raise ValueError(f'Selected submitted TSV identity mismatch: {path}')
    code = stage / 'code/business_entity_resolution' if reuse_stage else stage_bundle(stage, model_root)
    manifest = json.loads((code / 'reproduction_manifest.json').read_text(encoding='utf-8'))
    if manifest['outputs'] != {'matching_results.tsv': MATCH_SHA, 'candidate_pairs.tsv': CAND_SHA}:
        raise ValueError('Staged selection manifest disagrees with V13')
    for item in manifest['model_files']:
        if digest(code / item['path']) != item['sha256']:
            raise ValueError(f'Staged checkpoint hash mismatch: {item["path"]}')
    mappings = {'output/matching_results.tsv': matching, 'output/candidate_pairs.tsv': candidate}
    for path in stage.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            mappings[path.relative_to(stage).as_posix()] = path
    for name in mappings:
        if name.endswith(('.py', '.cpp', '.h')) and not name.startswith('code/business_entity_resolution/src/'):
            raise ValueError(f'Source file outside required src directory: {name}')
        if name.endswith(('.pdf', '.pyc')) or '/.env' in name:
            raise ValueError(f'Forbidden package artifact: {name}')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=4, allowZip64=True) as archive:
        for name, path in sorted(mappings.items()):
            archive.write(path, name)
    with zipfile.ZipFile(temporary) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f'ZIP integrity failure: {bad}')
        for name, expected in (('output/matching_results.tsv', MATCH_SHA), ('output/candidate_pairs.tsv', CAND_SHA)):
            with archive.open(name) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError(f'Archived TSV identity mismatch: {name}')
    temporary.replace(output)
    receipt = {'archive': str(output.resolve()), 'archive_bytes': output.stat().st_size,
               'archive_sha256': digest(output), 'matching_sha256': MATCH_SHA, 'candidate_sha256': CAND_SHA,
               'selected_version': 'v13-country-owner', 'public_score': .969, 'entries': len(mappings),
               'zip_crc': 'PASS', 'archived_tsv_identity': 'PASS', 'staged_code': str(code.resolve())}
    (output.parent / 'final_package_receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matching', type=Path, default=ROOT / 'output/submission_v13_owner_country/matching_results.tsv')
    parser.add_argument('--candidate', type=Path, default=ROOT / 'output/submission_v5_neural32/candidate_pairs.tsv')
    parser.add_argument('--models', type=Path, default=ROOT / 'artifacts/final_v13_models')
    parser.add_argument('--stage', type=Path, default=ROOT / 'artifacts/final_v13_package')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/Team_517_submission.zip')
    parser.add_argument('--stage-only', action='store_true', help='Prepare source/checkpoints for audit before compression')
    parser.add_argument('--reuse-stage', action='store_true', help='Compress the previously audited staging directory')
    args = parser.parse_args()
    if args.stage_only:
        print(stage_bundle(args.stage, args.models))
    else:
        print(json.dumps(package(args.matching, args.candidate, args.output, args.models, args.stage, args.reuse_stage), indent=2))


if __name__ == '__main__':
    main()
