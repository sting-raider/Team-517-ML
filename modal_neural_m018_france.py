"""M018 France-only inference on the frozen V5 candidate pool.

The matched French rows replace V6's French rows. All other countries and
the exact audited candidate_pairs.tsv remain unchanged.
"""
import gzip
import json
import shutil
from pathlib import Path

import modal

from modal_app import VOLUME_ROOT, SCRATCH, volume

gpu_image = (modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent / 'requirements.txt'))
    .pip_install('torch==2.8.0', 'transformers==4.57.1',
                 'huggingface_hub==0.36.0', 'sentencepiece==0.2.1',
                 'faiss-cpu==1.12.0')
    .env({'PYTHONPATH': '/app/src'})
    .add_local_dir(str(Path(__file__).parent / 'src'), '/app/src')
    .add_local_python_source('modal_app'))
cpu_image = (modal.Image.debian_slim(python_version='3.12')
    .pip_install_from_requirements(str(Path(__file__).parent / 'requirements.txt'))
    .env({'PYTHONPATH': '/app/src'})
    .add_local_dir(str(Path(__file__).parent / 'src'), '/app/src')
    .add_local_python_source('modal_app'))
app = modal.App('team517-m018-france-test')
ROOT = VOLUME_ROOT / 'project/output'
RUN = 'submission_v7_m018_france'


@app.function(image=gpu_image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, gpu='L4', timeout=14400)
def score(part: int):
    from ber.predict_neural import score_partition
    from ber.predict import sha256

    if not 0 <= part < 4:
        raise ValueError('Expected France partition 0..3')
    db = SCRATCH / 'artifacts/m018_france.duckdb'
    db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VOLUME_ROOT / 'project/artifacts/data_v3.duckdb', db)
    out = ROOT / f'{RUN}_part{part}of4'
    result = score_partition(
        db, VOLUME_ROOT / 'project/experiments/int005_test_retrieval',
        VOLUME_ROOT / 'project/experiments/int005/encoder',
        VOLUME_ROOT / 'project/experiments/m018/model', out,
        'France', part, 4, .95, batch_size=5000,
        checkpoint=volume.commit,
        cat_path=VOLUME_ROOT / 'project/experiments/int003/depth10/mixed.cbm',
        dense_prior=-2.)
    original = ROOT / f'submission_v5_neural32_part{part}of12'
    expected = json.loads((original / 'completion.json').read_text())
    if result['candidate_sha256'] != expected['candidate_sha256'] or \
            sha256(out / 'candidate_pairs.tsv') != expected['candidate_sha256']:
        raise ValueError('M018 rerun changed the frozen France candidate pool')
    volume.commit()
    return result


@app.function(image=cpu_image, volumes={str(VOLUME_ROOT): volume}, cpu=4,
              memory=16384, timeout=3600)
def merge():
    from ber.predict import sha256
    from ber.recover_blank import recover

    by_anchor = {}
    expected_france = 0
    for part in range(4):
        folder = ROOT / f'{RUN}_part{part}of4'
        receipt = json.loads((folder / 'completion.json').read_text())
        if sha256(folder / 'matching_results.tsv') != receipt['matching_sha256']:
            raise ValueError('France partition checksum mismatch')
        expected_france += receipt['anchors']
        with (folder / 'matching_results.tsv').open(encoding='utf-8') as stream:
            if stream.readline() != 'source1_entity_id\tmatched_entity_ids\n':
                raise ValueError('Invalid partition header')
            for line in stream:
                anchor, ids = line.rstrip('\r\n').split('\t', 1)
                if anchor in by_anchor:
                    raise ValueError('Duplicate French anchor')
                by_anchor[anchor] = ids
    if expected_france != 259452 or len(by_anchor) != expected_france:
        raise ValueError('Incomplete French output')

    out = ROOT / RUN
    out.mkdir(parents=True, exist_ok=True)
    base = ROOT / 'submission_v6_blank_recovery/matching_results.tsv'
    old = json.loads((ROOT / 'submission_v6_blank_recovery/completion.json').read_text())
    if sha256(base) != old['matching_sha256']:
        raise ValueError('V6 base checksum mismatch')
    intermediate = out / 'before_blank_recovery.tsv'
    rows = replaced = 0
    with base.open(encoding='utf-8') as src, intermediate.open('w', encoding='utf-8') as dst:
        if src.readline() != 'source1_entity_id\tmatched_entity_ids\n':
            raise ValueError('Invalid V6 header')
        dst.write('source1_entity_id\tmatched_entity_ids\n')
        for line in src:
            anchor, ids = line.rstrip('\r\n').split('\t', 1)
            if anchor in by_anchor:
                ids = by_anchor.pop(anchor)
                replaced += 1
            dst.write(anchor + '\t' + ids + '\n')
            rows += 1
    if rows != 1732544 or replaced != expected_france or by_anchor:
        raise ValueError('V7 row/France coverage mismatch')
    candidate = ROOT / 'submission_v5_neural32/candidate_pairs.tsv'
    v5 = json.loads((ROOT / 'submission_v5_neural32/completion.json').read_text())
    if sha256(candidate) != v5['candidate_sha256']:
        raise ValueError('Frozen candidate checksum mismatch')
    recovered = recover(VOLUME_ROOT / 'project/artifacts/data_v3.duckdb',
                        candidate, intermediate, out / 'matching_results.tsv')
    matching = out / 'matching_results.tsv'
    compressed = out / 'matching_results.tsv.gz'
    with matching.open('rb') as src, compressed.open('wb') as dst:
        with gzip.GzipFile(filename='', mode='wb', fileobj=dst,
                           compresslevel=3, mtime=0) as gz:
            shutil.copyfileobj(src, gz, 1 << 20)
    report = {'rows': rows, 'france_replaced': replaced,
              'candidate_sha256': v5['candidate_sha256'],
              'matching_sha256': sha256(matching),
              'compressed_sha256': sha256(compressed),
              'compressed_bytes': compressed.stat().st_size,
              'blank_recovery': recovered}
    (out / 'completion.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    volume.commit()
    return report


@app.local_entrypoint()
def main(action: str = 'run'):
    if action == 'score':
        calls = [score.spawn(part) for part in range(4)]
        for call in calls:
            result = call.get()
            print('M018 France part', result['partition'], result['anchors'], flush=True)
        return
    if action == 'merge':
        report = merge.remote()
        Path('reports/m018_france_submission.json').write_text(
            json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2), flush=True)
        return
    raise ValueError('Expected --action score or merge')
