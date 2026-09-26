"""INT004 empirical follow-up to M004: v3 retrieval plus address alignment."""
import json
import shutil
from pathlib import Path

import modal
from modal_app import image, volume, _enable_native_features, SCRATCH, VOLUME_ROOT

image = image.add_local_python_source('modal_app')
app = modal.App('team517-v4')
ROOT = VOLUME_ROOT / 'project/experiments/int004'
V3_DB = VOLUME_ROOT / 'project/artifacts/data_v3.duckdb'
BASELINE = VOLUME_ROOT / 'project/experiments/int003/depth10'


def copy_database():
    dest = SCRATCH / 'artifacts/data_v3.duckdb'
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(V3_DB, dest)
    return dest


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, timeout=3600)
def make_features(partition: int, partitions: int = 8, confirmation: bool = False):
    _enable_native_features()
    from ber.v4 import V4_NAMES, materialize
    section = 'confirmation' if confirmation else 'features'
    out = ROOT / section / f'part{partition}'
    if (out / 'ready.json').exists():
        receipt = json.loads((out / 'ready.json').read_text())
        if (receipt['feature_names'] != V4_NAMES or
                receipt['partitions'] != partitions or
                receipt['partition'] != partition or
                receipt['confirmation'] != confirmation):
            raise ValueError('Stale feature cache')
        return receipt
    result = materialize(copy_database(), out, partition, partitions, confirmation)
    volume.commit()
    return result


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=65536, gpu='L4', timeout=3600)
def train_model(depth: int = 10):
    from ber.v2 import train
    from ber.v3 import V3_NAMES
    from ber.v4 import V4_NAMES
    report = train(ROOT / 'features', ROOT / f'depth{depth}', BASELINE,
                   depth=depth, feature_names=V4_NAMES, feature_version=4,
                   baseline_feature_count=len(V3_NAMES), baseline_threshold=.625,
                   blocker='lexical+char-rrf160-average-tie-rank')
    volume.commit()
    return report


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=16384, timeout=1800)
def confirm_model(depth: int = 10):
    import numpy as np
    from catboost import CatBoostClassifier
    from ber.v2 import load_parts, score_slices
    from ber.v3 import V3_NAMES
    from ber.v4 import V4_NAMES
    from ber.experiment import mappings
    from ber.metrics import row_score
    from ber.predict import sha256

    x, y, groups, targets, meta = load_parts(ROOT / 'confirmation', 1, V4_NAMES)
    folder = ROOT / f'depth{depth}'
    config = json.loads((folder / 'model_config.json').read_text())
    model = CatBoostClassifier()
    model.load_model(str(folder / 'mixed.cbm'))
    baseline = CatBoostClassifier()
    baseline.load_model(str(BASELINE / 'mixed.cbm'))
    current_prob = model.predict_proba(x, thread_count=8)[:, 1]
    prior_prob = baseline.predict_proba(x[:, :len(V3_NAMES)], thread_count=8)[:, 1]
    indices = range(len(meta))
    truth, current, candidates = mappings(meta, groups, targets, current_prob,
                                          indices, config['threshold'])
    _, prior, _ = mappings(meta, groups, targets, prior_prob, indices, .625)
    delta = np.array([row_score(truth[k], current[k]) - row_score(truth[k], prior[k])
                      for k in truth])
    rng = np.random.default_rng(517)
    boot = np.array([rng.choice(delta, size=len(delta), replace=True).mean()
                     for _ in range(2000)])
    report = {
        'protocol': 'Fresh hash positions 200001:205000; same fused candidate pool and first 57 feature columns for frozen INT003 baseline',
        'model_sha256': sha256(folder / 'mixed.cbm'),
        'v3': score_slices(meta, groups, targets, prior_prob, 'confirmation', .625),
        'v4': score_slices(meta, groups, targets, current_prob, 'confirmation', config['threshold']),
        'paired_delta': float(delta.mean()),
        'paired_bootstrap_95': np.quantile(boot, [.025, .975]).tolist(),
        'improved_entities': int((delta > 0).sum()),
        'regressed_entities': int((delta < 0).sum()),
        'seed': 517, 'resamples': 2000,
    }
    (folder / 'confirmation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    volume.commit()
    return report


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, timeout=3600)
def score_partition(depth: int, partition: int, partitions: int = 8):
    import threading
    _enable_native_features()
    from ber.predict import predict
    db = copy_database()
    out = VOLUME_ROOT / 'project/output' / f'submission_v4_d{depth}_part{partition}of{partitions}'
    stop = threading.Event()

    def checkpoint():
        while not stop.wait(180):
            volume.commit()

    thread = threading.Thread(target=checkpoint, daemon=True)
    thread.start()
    try:
        predict(db, ROOT / f'depth{depth}', out, batch_size=10000, workers=8,
                query_batches=1, partition_index=partition, partition_count=partitions)
    finally:
        stop.set()
        thread.join(timeout=30)
        volume.commit()
    return str(out)


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=4,
              memory=16384, timeout=1800)
def merge_prediction(depth: int, partitions: int = 8):
    from modal_app import merge_score
    return merge_score.local(f'submission_v4_d{depth}', partitions, 160)


@app.local_entrypoint()
def main(action: str = 'train', depth: int = 10):
    if action == 'train':
        calls = [make_features.spawn(i) for i in range(8)]
        for i, call in enumerate(calls):
            receipt = call.get()
            print(f'Feature partition {i}: {receipt["anchors"]} anchors', flush=True)
        report = train_model.remote(depth)
        Path(f'reports/int004_depth{depth}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Trained v4', flush=True)
    elif action == 'confirm':
        receipt = make_features.remote(0, 1, True)
        print(f'Fresh confirmation: {receipt["anchors"]} anchors', flush=True)
        report = confirm_model.remote(depth)
        Path(f'reports/int004_depth{depth}_confirmation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2), flush=True)
    elif action == 'score':
        calls = [score_partition.spawn(depth, i) for i in range(8)]
        for call in calls:
            print(call.get(), flush=True)
        report = merge_prediction.remote(depth)
        Path(f'reports/int004_depth{depth}_export.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2), flush=True)
    else:
        raise ValueError(f'Unknown action: {action}')
