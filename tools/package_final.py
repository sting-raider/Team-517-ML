"""Build the required final zip from the exact, checksum-verified TSV pair."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
MATCH_SHA='ab1b41964cdfbbccb4956c47d362d6c9b08cf7de73d67c3c8b66a963f61010e5'
CAND_SHA='fa286e237b9bdd31905f901d2a1449771698249d4c1dfe45dcbfa38bf647c3ec'
CORE_MODAL=(
    'modal_app.py','modal_v2.py','modal_v3.py','modal_dense.py',
    'modal_crossencoder.py','modal_dense_test.py',
    'modal_neural_submission.py','modal_recover_blank.py')
REPORTS=(
    'reports/swarm/INT005-D017-learned-owner-competition.md',
    'reports/swarm/M017-multilingual-crossencoder.md',
    'reports/swarm/INT006-neural32-integration.md',
    'reports/swarm/INT007-blank-address-recovery.md',
    'reports/capped_match_evaluation.json',
    'reports/neural32_submission.json',
    'reports/blank_recovery_submission.json')


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8<<20),b''):
            value.update(chunk)
    return value.hexdigest()


def package(matching,candidate,output):
    matching=Path(matching)
    candidate=Path(candidate)
    output=Path(output)
    for path,expected in ((matching,MATCH_SHA),(candidate,CAND_SHA)):
        actual=digest(path)
        if actual!=expected:
            raise ValueError(f'{path}: SHA-256 {actual} does not match expected {expected}')
    code=ROOT/'submission'
    mappings={
        'output/matching_results.tsv':matching,
        'output/candidate_pairs.tsv':candidate,
        'Documentation_template.md':ROOT/'Documentation_template.md',
        'code/business_entity_resolution/README.md':code/'README.md',
        'code/business_entity_resolution/requirements.txt':code/'requirements.txt',
        'code/business_entity_resolution/requirements-gpu.txt':code/'requirements-gpu.txt',
        'code/business_entity_resolution/pyproject.toml':ROOT/'pyproject.toml',
        'code/business_entity_resolution/tools/stage_modal.py':ROOT/'tools/stage_modal.py'}
    for name in CORE_MODAL+REPORTS:
        mappings[f'code/business_entity_resolution/{name}']=ROOT/name
    for path in (ROOT/'src').rglob('*'):
        if path.is_file() and path.suffix in ('.py','.cpp','.h'):
            mappings[f'code/business_entity_resolution/{path.relative_to(ROOT).as_posix()}']=path
    missing=[str(path) for path in mappings.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError('Package inputs missing: '+', '.join(missing))
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix(output.suffix+'.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,
                         compresslevel=4,allowZip64=True) as archive:
        for arcname,path in sorted(mappings.items()):
            archive.write(path,arcname)
    temporary.replace(output)
    receipt={'archive':str(output.resolve()),'archive_bytes':output.stat().st_size,
             'archive_sha256':digest(output),'matching_sha256':MATCH_SHA,
             'candidate_sha256':CAND_SHA,'entries':len(mappings)}
    (output.parent/'final_package_receipt.json').write_text(
        json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--matching',type=Path,
        default=ROOT/'output/submission_v6_blank_recovery/matching_results.tsv')
    parser.add_argument('--candidate',type=Path,
        default=ROOT/'output/submission_v5_neural32/candidate_pairs.tsv')
    parser.add_argument('--output',type=Path,
        default=ROOT/'output/Team_517_submission.zip')
    args=parser.parse_args()
    print(json.dumps(package(args.matching,args.candidate,args.output),indent=2))


if __name__=='__main__':
    main()
