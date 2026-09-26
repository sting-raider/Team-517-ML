"""Full-inventory competing-owner diagnostics; never inject a labeled owner."""
import json
import time
from pathlib import Path

import numpy as np


def prepare(db, baseline, out, fold='calibrate'):
    from .data import connect
    from .blocking import build_index
    from .retrieval_v3 import build_char_index, fused_candidates

    started = time.monotonic()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((Path(baseline) / 'anchors.json').read_text())
    selected = {i: m for i, m in enumerate(meta) if m['fold'] == fold}
    with np.load(Path(baseline) / 'evaluation.npz') as z:
        keep = np.isin(z['groups'], list(selected)) & (z['prob'] >= .625)
        edges = [(str(t), meta[int(g)]['id'], float(p)) for g, t, p in
                 zip(z['groups'][keep], z['target'][keep], z['prob'][keep])]
    (out / 'evaluation.json').write_text(json.dumps({
        'meta': list(selected.values()), 'predictions': edges}), encoding='utf-8')
    c = connect(db)
    c.execute("SET memory_limit='22GB'")
    c.execute('SET threads=8')
    # Reuse the bounded blocker against the complete CLEAN source-one inventory.
    c.execute('''CREATE TABLE reverse_train AS
        SELECT * REPLACE (2 AS source) FROM train WHERE source=1''')
    build_index(c, 'reverse_train')
    build_char_index(c, 'reverse_train')
    c.execute('CREATE TEMP TABLE original(target VARCHAR, owner VARCHAR, probability DOUBLE)')
    c.executemany('INSERT INTO original VALUES (?,?,?)', edges)
    c.execute('''CREATE TEMP TABLE queries AS SELECT t.* FROM train t
        JOIN (SELECT DISTINCT target FROM original) q ON t.entity_id=q.target''')
    fused_candidates(c, 'reverse_train', 'queries', 'reverse_candidates', 32)
    c.execute('''CREATE TEMP TABLE owner_pairs AS
        SELECT p.anchor AS target, r.entity_id AS owner FROM reverse_candidates p
        JOIN reverse_train r ON p.rid=r.rowid
        UNION SELECT target,owner FROM original''')
    # Original forward candidates are retained, irrespective of reverse retrieval.
    c.execute('''COPY (SELECT p.target,p.owner,l.n AS ln,l.a AS la,r.n AS rn,r.a AS ra
        FROM owner_pairs p JOIN train l ON p.owner=l.entity_id
        JOIN train r ON p.target=r.entity_id) TO ? (FORMAT PARQUET)''', [str(out/'pairs.parquet')])
    c.execute('''COPY (SELECT t.entity_id,t.business_name,t.business_address
        FROM train t JOIN (SELECT target AS entity_id FROM owner_pairs UNION
        SELECT owner AS entity_id FROM owner_pairs) ids USING(entity_id))
        TO ? (FORMAT PARQUET)''', [str(out/'records.parquet')])
    report = {'fold': fold, 'anchors': len(selected), 'forward_edges': len(edges),
              'queried_targets': c.execute('SELECT count(*) FROM queries').fetchone()[0],
              'owner_candidates': c.execute('SELECT count(*) FROM owner_pairs').fetchone()[0],
              'reverse_cap': 32, 'seconds': time.monotonic()-started,
              'protocol': 'Complete S1 inventory; reverse lexical/character cap32 plus original forward predictions; no labeled-owner injection'}
    (out/'prepare.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    c.close()
    return report


def encode_records(records, encoder, batch_size=512):
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer
    from .dense_training import serialize

    torch.set_num_threads(4)
    tokenizer = AutoTokenizer.from_pretrained(encoder)
    model = AutoModel.from_pretrained(encoder).eval().cuda()
    texts = [serialize(n, a) for _, n, a in records]
    vectors = np.empty((len(texts), model.config.hidden_size), np.float32)
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    started = time.monotonic()
    with torch.inference_mode():
        for offset in range(0, len(order), batch_size):
            indices = order[offset:offset+batch_size]
            inputs = tokenizer([texts[i] for i in indices], padding=True, truncation=True,
                               max_length=128, return_tensors='pt').to('cuda')
            with torch.autocast('cuda', dtype=torch.bfloat16):
                hidden = model(**inputs).last_hidden_state
                mask = inputs['attention_mask'].unsqueeze(-1)
                values = F.normalize((hidden.float()*mask).sum(1)/mask.sum(1).clamp_min(1), dim=1)
            vectors[indices] = values.cpu().numpy()
            if offset % (batch_size*50) == 0:
                print(f'Encoded {offset+len(indices)}/{len(texts)}; {time.monotonic()-started:.1f}s', flush=True)
    return {r[0]: i for i,r in enumerate(records)}, vectors


def evaluate_owners(root, encoder):
    import duckdb
    from rapidfuzz import fuzz
    from .metrics import evaluate

    root = Path(root)
    started = time.monotonic()
    c = duckdb.connect()
    records = c.execute('SELECT * FROM read_parquet(?)', [str(root/'records.parquet')]).fetchall()
    lookup, vectors = encode_records(records, encoder)
    pairs = c.execute('SELECT * FROM read_parquet(?) ORDER BY target,owner', [str(root/'pairs.parquet')]).fetchall()
    meta = json.loads((root/'evaluation.json').read_text())
    truth = {m['id']: m['truth'] for m in meta['meta']}
    original = {}
    for target, owner, probability in meta['predictions']:
        original.setdefault(owner, set()).add(target)
    scores = {'dense': {}, 'address': {}, 'joint_text': {}}
    best = {k: {} for k in scores}
    for target, owner, ln, la, rn, ra in pairs:
        # IDs only join vectors. They never determine a competing-owner score.
        name = fuzz.ratio(ln, rn)/100
        address = (fuzz.ratio(la,ra)+fuzz.token_sort_ratio(la,ra))/200 if la and ra else 0.
        values = {'dense': float(vectors[lookup[target]] @ vectors[lookup[owner]]),
                  'address': address, 'joint_text': .2*name+.8*address}
        for method, value in values.items():
            scores[method][target,owner] = value
            best[method][target] = max(best[method].get(target, -2.), value)
    def metrics(pred):
        result = evaluate(truth, pred)
        result['countries'] = {co: evaluate({m['id']:m['truth'] for m in meta['meta'] if m['country']==co},pred)
                               for co in sorted({m['country'] for m in meta['meta']})}
        return result
    report = {'protocol': json.loads((root/'prepare.json').read_text()),
              'baseline': metrics(original), 'variants': {}}
    for method in scores:
        for margin in (0., .02, .05, .1):
            pred = {}
            removed_tp = removed_fp = 0
            for target, owner, probability in meta['predictions']:
                # Remove only when an alternative is strictly stronger. A tie is
                # retained; arbitrary ID ordering must not become identity evidence.
                if best[method][target] > scores[method][target,owner]+margin+1e-7:
                    removed_tp += target in truth[owner]
                    removed_fp += target not in truth[owner]
                else:
                    pred.setdefault(owner,set()).add(target)
            value = metrics(pred)
            value.update(removed_true_edges=removed_tp,removed_false_edges=removed_fp)
            report['variants'][f'{method}_margin{margin}'] = value
    report['seconds'] = time.monotonic()-started
    np.savez(root/'pair_scores.npz', target=np.array([p[0] for p in pairs]),
             owner=np.array([p[1] for p in pairs]),
             **{k: np.array([v[p[0],p[1]] for p in pairs]) for k,v in scores.items()})
    (root/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
