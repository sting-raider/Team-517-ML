"""Private full-data gate for M001 IDF-weighted INT003 pair features.

This runner deliberately exposes prepare/train only. Promotion requires a
same-candidate development result before any confirmation or test scoring path
is added.
"""
import json
import shutil
from pathlib import Path

import modal
from modal_app import SCRATCH, VOLUME_ROOT, _enable_native_features, image, volume

image = image.add_local_python_source('modal_app')
app = modal.App('team517-m001c')
ROOT = VOLUME_ROOT/'project/experiments/m001c'
V3_DB = VOLUME_ROOT/'project/artifacts/data_v3.duckdb'
M001_DB = VOLUME_ROOT/'project/artifacts/data_m001c.duckdb'


def copy_database():
    dest = SCRATCH/'artifacts/data_m001c.duckdb'
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(M001_DB, dest)
    return dest


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8, memory=32768, timeout=3600)
def prepare_database():
    from ber.data import connect
    from ber.idf import IDF_VERSION, build_token_idf_tables

    receipt = ROOT/'database_ready.json'
    if receipt.exists():
        meta = json.loads(receipt.read_text())
        if (meta.get('source_bytes') != V3_DB.stat().st_size or
                meta.get('idf_version') != IDF_VERSION or not M001_DB.exists()):
            raise ValueError('Prepared M001 database is stale')
        return meta

    work = SCRATCH/'artifacts/data_m001c.duckdb'
    work.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(V3_DB, work)
    c = connect(work)
    c.execute("SET memory_limit='20GB'")
    c.execute('SET threads=8')
    profiles = {split: build_token_idf_tables(c, split) for split in ('train', 'test')}
    c.execute('CHECKPOINT')
    c.close()

    staging = M001_DB.with_suffix('.duckdb.tmp')
    shutil.copy2(work, staging)
    staging.replace(M001_DB)
    ROOT.mkdir(parents=True, exist_ok=True)
    meta = {
        'idf_version': IDF_VERSION,
        'source_bytes': V3_DB.stat().st_size,
        'database_bytes': M001_DB.stat().st_size,
        'profiles': profiles,
        'semantics': 'country+concrete-source+field token DF; pair weight=mean(left IDF,right IDF)',
    }
    receipt.write_text(json.dumps(meta, indent=2), encoding='utf-8')
    volume.commit()
    return meta


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8, memory=32768, timeout=3600)
def make_features(partition: int, partitions: int = 8):
    _enable_native_features()
    from ber.v5 import V5_NAMES, materialize

    out = ROOT/'features'/f'part{partition}'
    if (out/'ready.json').exists():
        meta = json.loads((out/'ready.json').read_text())
        if (meta['feature_names'] != V5_NAMES or meta['partitions'] != partitions or
                meta['partition'] != partition):
            raise ValueError('Stale or mismatched M001 feature cache')
        return meta
    result = materialize(copy_database(), out, partition, partitions)
    volume.commit()
    return result


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8, memory=65536, gpu='L4', timeout=3600)
def train_model(depth: int = 10):
    from ber.v2 import train
    from ber.v3 import V3_NAMES
    from ber.v5 import V5_NAMES

    result = train(
        ROOT/'features', ROOT/f'depth{depth}',
        VOLUME_ROOT/'project/experiments/int003/depth10', depth=depth,
        feature_names=V5_NAMES, feature_version=5,
        baseline_feature_count=len(V3_NAMES), baseline_threshold=.6250000000000002,
        blocker='lexical+char-rrf160-average-tie-rank+idf-pair',
    )
    expected = {
        'calibrate': (0.9491209587754517, 0.944357161560618, 0.9804608439335135),
        'holdout': (0.9447832214793936, 0.9450685453160701, 0.9793001848908854),
    }
    for split, values in expected.items():
        measured = result['baseline'][split]['all']
        actual = (measured['macro_f0_5'], measured['candidate_pair_recall'],
                  measured['blocking_oracle_macro_f0_5'])
        if any(abs(a-b) > 1e-12 for a,b in zip(actual, values)):
            raise ValueError(f'INT003 same-candidate parity failed on {split}: {actual} != {values}')
    volume.commit()
    return result


@app.local_entrypoint()
def main(action: str = 'prepare', depth: int = 10):
    if action == 'prepare':
        result = prepare_database.remote()
        Path('reports/m001c_database.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    elif action == 'train':
        prepare_database.remote()
        calls = [make_features.spawn(i) for i in range(8)]
        for i, call in enumerate(calls):
            receipt = call.get()
            print(f'Feature partition {i}: {receipt["anchors"]} anchors', flush=True)
        result = train_model.remote(depth)
        Path(f'reports/m001c_depth{depth}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2), flush=True)
    else:
        raise ValueError('M001c only supports prepare/train before empirical promotion')
