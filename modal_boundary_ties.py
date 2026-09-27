"""I039: audit exact-score ID dependence at INT006 dense16/final32 boundaries."""
import json
import shutil
from pathlib import Path

import modal
from modal_app import image, volume, VOLUME_ROOT, SCRATCH

cpu_image = (image
    .env({'PYTHONPATH': '/app/src'})
    .add_local_dir(str(Path(__file__).parent / 'src'), '/app/src')
    .add_local_python_source('modal_app'))
app = modal.App('team517-i039-neural32-boundary-ties')
ROOT = VOLUME_ROOT / 'project/experiments/int005_retrieval'
FEATURES = VOLUME_ROOT / 'project/experiments/int003/depth10'
DB = VOLUME_ROOT / 'project/artifacts/data_v3.duckdb'

EXPECTED = {
    ('calibrate', 'India'): (0.9747623729924615, 0.992386381132954),
    ('calibrate', 'US'): (0.9825594070198387, 0.994937691471096),
    ('holdout', 'India'): (0.9728473581213307, 0.9914192778520664),
    ('holdout', 'US'): (0.982076059850374, 0.993748189818689),
}


def _set_delta(left, right):
    anchors = 0
    pairs = 0
    for anchor in left:
        diff = left[anchor] ^ right[anchor]
        if diff:
            anchors += 1
            pairs += len(diff)
    return {'anchors_changed': anchors, 'symmetric_difference_pairs': pairs}


@app.function(image=cpu_image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, timeout=1800)
def audit(country: str, fold: str):
    import numpy as np
    from ber.boundary_ties import boundary_tie, rank_rows, select_final_pool, summarize_ties
    from ber.data import connect
    from ber.metrics import evaluate
    from ber.retrieval_v3 import fused_candidates

    if country not in ('India', 'US') or fold not in ('calibrate', 'holdout'):
        raise ValueError('I039 is restricted to labeled India/US calibration/holdout')
    prefix = 'cal' if fold == 'calibrate' else 'hold'
    meta = json.loads((FEATURES / 'anchors.json').read_text())
    truth = {m['id']: set(m['truth']) for m in meta
             if m['fold'] == fold and m['country'] == country}
    if not truth:
        raise ValueError('No anchors for requested country/fold')

    local = SCRATCH / f'artifacts/i039_{country}_{fold}.duckdb'
    local.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DB, local)
    c = connect(local)
    c.execute("SET memory_limit='24GB'")
    c.execute('SET threads=8')
    c.execute('CREATE TEMP TABLE i039_ids AS SELECT unnest(?) entity_id', [sorted(truth)])
    c.execute('''CREATE TEMP TABLE i039_anchors AS SELECT t.* FROM train t
        JOIN i039_ids i USING(entity_id) WHERE source=1''')
    if c.execute('SELECT count(*) FROM i039_anchors').fetchone()[0] != len(truth):
        raise ValueError('Anchor universe mismatch')

    # Reconstruct the exact v3 base channel. Production later pre-caps this
    # table to 32 by retrieval DESC, entity_id ASC.
    fused_candidates(c, 'train', 'i039_anchors', 'i039_base160', 160)
    base = {anchor: [] for anchor in truth}
    rid_to_entity = {}
    for anchor, rid, score, entity in c.execute('''SELECT p.anchor,p.rid,p.retrieval,t.entity_id
        FROM i039_base160 p JOIN train t ON p.rid=t.rowid
        ORDER BY p.anchor,p.retrieval DESC,t.entity_id''').fetchall():
        row = (float(score), str(entity), int(rid))
        base[str(anchor)].append(row)
        rid_to_entity[int(rid)] = str(entity)

    # Saved searches contain top64 per target shard. Local capped evaluation
    # re-sorts all of them using (score,rowid) DESC, whereas production asks
    # Faiss for top16 per shard first.
    shards = [{anchor: [] for anchor in truth} for _ in range(4)]
    all_ann_rids = set()
    for part in range(4):
        path = ROOT / country / f'part{part}' / f'{prefix}_nprobe64.npz'
        if not path.exists():
            raise FileNotFoundError(f'Missing saved ANN artifact: {path}')
        with np.load(path) as z:
            ids, rowids, scores = z['anchor'], z['rowid'], z['similarity']
            for i, raw_anchor in enumerate(ids):
                anchor = str(raw_anchor)
                if anchor not in truth:
                    continue
                rows = []
                for score, rid in zip(scores[i], rowids[i]):
                    rid = int(rid)
                    if rid < 0:
                        continue
                    rows.append((float(score), rid, rid))
                    all_ann_rids.add(rid)
                shards[part][anchor] = rows

    # Map ANN rowids to supplied target IDs in bounded chunks. IDs are used for
    # existence/evaluation only, never as model features.
    missing = sorted(all_ann_rids - set(rid_to_entity))
    for start in range(0, len(missing), 100000):
        chunk = missing[start:start + 100000]
        for rid, entity in c.execute('''SELECT rowid,entity_id FROM train
            WHERE rowid IN (SELECT unnest(?))''', [chunk]).fetchall():
            rid_to_entity[int(rid)] = str(entity)
    if any(rid not in rid_to_entity for rid in all_ann_rids):
        raise ValueError('ANN returned a rowid absent from the supplied target inventory')

    shard_ties = []
    merged_ties = []
    base32_ties = []
    final_base_ties = []
    eval_pool = {}
    prefix_pool = {}
    alt_pool = {}

    for anchor in truth:
        truth_ids = truth[anchor]
        per_shard = []
        for part in range(4):
            raw = shards[part][anchor]
            entity_rows = [(s, rid, rid_to_entity[rid]) for s, rid, _ in raw]
            shard_ties.append(boundary_tie(entity_rows, 16, truth_items=truth_ids))
            per_shard.append(raw)

        all_rows = [row for rows in per_shard for row in rows]
        eval_dense = rank_rows(all_rows, tie_desc=True)[:16]
        prefix_rows = [row for rows in per_shard for row in rows[:16]]
        prefix_dense = rank_rows(prefix_rows, tie_desc=True)[:16]
        alt_dense = rank_rows(all_rows, tie_desc=False)[:16]

        merged_entity = [(s, rid, rid_to_entity[rid])
                         for s, rid, _ in rank_rows(all_rows, tie_desc=True)]
        merged_ties.append(boundary_tie(merged_entity, 16, truth_items=truth_ids))

        base_rows = base[anchor]
        base_entity = [(s, tie_id, rid_to_entity[rid]) for s, tie_id, rid in base_rows]
        base32_ties.append(boundary_tie(base_entity, 32, truth_items=truth_ids))

        dense_rids = {row[2] for row in eval_dense}
        eligible = [row for row in base_rows if row[2] not in dense_rids]
        eligible_entity = [(s, tie_id, rid_to_entity[rid]) for s, tie_id, rid in eligible]
        final_base_ties.append(boundary_tie(eligible_entity, 16, truth_items=truth_ids))

        eval_rows = select_final_pool(eval_dense, base_rows, cap=32, base_pre_cap=32)
        prefix_rows_final = select_final_pool(prefix_dense, base_rows, cap=32, base_pre_cap=32)
        alt_base = rank_rows(base_rows, tie_desc=True)
        alt_rows_final = select_final_pool(alt_dense, alt_base, cap=32, base_pre_cap=32)

        eval_pool[anchor] = {rid_to_entity[row[2]] for row in eval_rows}
        prefix_pool[anchor] = {rid_to_entity[row[2]] for row in prefix_rows_final}
        alt_pool[anchor] = {rid_to_entity[row[2]] for row in alt_rows_final}

    def metrics(pool):
        oracle = {anchor: truth[anchor] & pool[anchor] for anchor in truth}
        return evaluate(truth, oracle, pool)

    eval_metrics = metrics(eval_pool)
    prefix_metrics = metrics(prefix_pool)
    alt_metrics = metrics(alt_pool)
    expected_pair, expected_oracle = EXPECTED[(fold, country)]
    if abs(eval_metrics['candidate_pair_recall'] - expected_pair) > 1e-12:
        raise ValueError('I039 failed INT006 candidate-pair-recall parity')
    if abs(eval_metrics['blocking_oracle_macro_f0_5'] - expected_oracle) > 1e-12:
        raise ValueError('I039 failed INT006 blocking-oracle parity')

    report = {
        'protocol': ('Exact existing INT006 calibration/holdout anchors; saved top64 ANN results from all four '
                     'full-inventory target shards; v3 base160 reconstructed from the complete supplied train inventory. '
                     'Truth is used only for evaluation/tie sensitivity.'),
        'country': country,
        'fold': fold,
        'anchors': len(truth),
        'dense_slots': 16,
        'candidate_cap': 32,
        'shard_dense16_boundary': summarize_ties(shard_ties, anchors=len(truth) * 4),
        'merged_dense16_boundary': summarize_ties(merged_ties, anchors=len(truth)),
        'base32_precap_boundary': summarize_ties(base32_ties, anchors=len(truth)),
        'final_base_fill_boundary': summarize_ties(final_base_ties, anchors=len(truth)),
        'local_eval_semantics': eval_metrics,
        'saved_prefix16_production_mirror': prefix_metrics,
        'reverse_id_tie_sensitivity': alt_metrics,
        'eval_vs_prefix_membership': _set_delta(eval_pool, prefix_pool),
        'eval_vs_reverse_id_membership': _set_delta(eval_pool, alt_pool),
        'expected_parity': {'candidate_pair_recall': expected_pair,
                            'blocking_oracle_macro_f0_5': expected_oracle,
                            'status': 'PASS'},
        'limitations': ('The saved-prefix16 mirror proves production parity only when no exact score tie crosses a '
                        'per-shard 16/17 boundary. If such ties exist, rerun the exact Faiss top16 query to determine '
                        'its selected members; do not infer them from labels.'),
    }
    c.close()
    return report


@app.local_entrypoint()
def main():
    reports = []
    for fold in ('calibrate', 'holdout'):
        for country in ('India', 'US'):
            value = audit.remote(country, fold)
            reports.append(value)
            print(f"{fold} {country}: shard tie rate={value['shard_dense16_boundary']['tie_rate']:.6g}; "
                  f"merged tie rate={value['merged_dense16_boundary']['tie_rate']:.6g}; "
                  f"eval/prefix changed anchors={value['eval_vs_prefix_membership']['anchors_changed']}",
                  flush=True)
    out = {'task': 'I039', 'reports': reports}
    Path('reports/i039_neural32_boundary_ties.json').write_text(
        json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps(out, indent=2), flush=True)
