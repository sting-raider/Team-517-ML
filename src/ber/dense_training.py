"""Supervised multilingual record retrieval; IDs are used only for labels/joins."""
import json
import math
import random
import time
from pathlib import Path

import numpy as np

MODEL = 'intfloat/multilingual-e5-small'
REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'


def serialize(name, address):
    return f'query: business name: {name}. address: {address}'


def prepare_partition(db, feature_root, model_path, out, partition):
    """Mine two hard negatives per fit anchor; retain ALL labeled positives."""
    from catboost import CatBoostClassifier
    from .data import connect
    from .v3 import V3_NAMES

    folder = Path(feature_root) / f'part{partition}'
    receipt = json.loads((folder / 'ready.json').read_text())
    if receipt['feature_names'] != V3_NAMES:
        raise ValueError('Expected frozen INT003 feature schema')
    meta = json.loads((folder / 'anchors.json').read_text())
    chosen = {i: m for i, m in enumerate(meta) if m['fold'] == 'fit' and m['truth']}
    negative = {}
    model = CatBoostClassifier()
    model.load_model(str(model_path))
    for chunk in receipt['chunks']:
        with np.load(folder / chunk) as arrays:
            groups = arrays['groups']
            keep = np.isin(groups, list(chosen)) & (arrays['y'] == 0)
            x, g, ids = arrays['x'][keep], groups[keep], arrays['target'][keep]
        probability = model.predict_proba(x, thread_count=8)[:, 1]
        order = np.lexsort((-probability, g))
        for j in order:
            values = negative.setdefault(int(g[j]), [])
            if len(values) < 2:
                values.append(str(ids[j]))
        print(f'INT005 part {partition}: mined {chunk}', flush=True)
    needed = set()
    for i, m in chosen.items():
        needed.add(m['id'])
        needed.update(m['truth'])
        needed.update(negative.get(i, []))
    c = connect(db)
    c.execute('CREATE TEMP TABLE dense_needed AS SELECT unnest(?) entity_id', [sorted(needed)])
    records = {i: serialize(n, a) for i,n,a in c.execute('''
        SELECT t.entity_id,t.business_name,t.business_address FROM train t
        JOIN dense_needed d USING(entity_id)''').fetchall()}
    if len(records) != len(needed):
        raise ValueError('Missing training record')
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = positives = 0
    with out.open('w', encoding='utf-8') as stream:
        for i, m in chosen.items():
            if not negative.get(i):
                continue
            row = {'anchor': m['id'], 'country': m['country'], 'query': records[m['id']],
                   'positives': [[t, records[t]] for t in m['truth']],
                   'negatives': [[t, records[t]] for t in negative[i]]}
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            count += 1
            positives += len(m['truth'])
    c.close()
    result = {'partition': partition, 'fit_anchors': count, 'available_positive_pairs': positives,
              'hard_negatives': sum(len(v) for v in negative.values()),
              'protocol': 'INT003 fit anchors only; all their labels, including positives absent from blocker; top two frozen-model negatives'}
    out.with_suffix('.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def train(root, out, epochs=1, batch_size=48, max_seconds=1800, checkpoint_callback=None):
    import torch
    import torch.nn.functional as F
    from huggingface_hub import HfApi
    from transformers import AutoModel, AutoTokenizer

    random.seed(517)
    np.random.seed(517)
    torch.manual_seed(517)
    torch.set_num_threads(4)
    info = HfApi().model_info(MODEL, revision=REVISION)
    license_name = info.card_data.get('license')
    if license_name != 'mit':
        raise ValueError('Pinned checkpoint license mismatch')
    rows = []
    for path in sorted(Path(root).glob('part*.jsonl')):
        with path.open(encoding='utf-8') as stream:
            rows.extend(json.loads(line) for line in stream)
    if len(rows) < 90000 or len({r['anchor'] for r in rows}) != len(rows):
        raise ValueError('Missing or overlapping fit partitions')
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    model = AutoModel.from_pretrained(MODEL, revision=REVISION).cuda()
    parameter_count = sum(p.numel() for p in model.parameters())
    if parameter_count > 8_000_000_000:
        raise ValueError('Competition parameter cap exceeded')
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=.01)
    total_steps = epochs * math.ceil(len(rows) / batch_size)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    step = 0
    losses = []
    model.train()
    rng = random.Random(517)
    stop = False
    for epoch in range(epochs):
        rng.shuffle(rows)
        for offset in range(0, len(rows), batch_size):
            batch = rows[offset:offset + batch_size]
            positives = [rng.choice(r['positives']) for r in batch]
            negatives = [pair for r in batch for pair in r['negatives']]
            candidates = positives + negatives
            texts = [r['query'] for r in batch] + [t for _,t in candidates]
            labels = [set(p[0] for p in r['positives']) for r in batch]
            positive_mask = torch.tensor([[i in label for i,_ in candidates] for label in labels],
                                         device='cuda', dtype=torch.bool)
            inputs = tokenizer(texts, padding=True, truncation=True, max_length=128,
                               return_tensors='pt').to('cuda')
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast('cuda', dtype=torch.bfloat16):
                hidden = model(**inputs).last_hidden_state
                mask = inputs['attention_mask'].unsqueeze(-1)
                embedding = F.normalize((hidden.float() * mask).sum(1) / mask.sum(1).clamp_min(1), dim=1)
                query, target = embedding[:len(batch)], embedding[len(batch):]
                logits = query @ target.T / .05
                loss = (torch.logsumexp(logits, dim=1) -
                        torch.logsumexp(logits.masked_fill(~positive_mask, -torch.inf), dim=1)).mean()
            if not torch.isfinite(loss):
                raise ValueError('Non-finite contrastive loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            warmup = min(1.0, (step + 1) / 100)
            decay = max(.1, 1 - step / max(1, total_steps))
            for group in optimizer.param_groups:
                group['lr'] = 2e-5 * warmup * decay
            optimizer.step()
            step += 1
            losses.append(float(loss.detach()))
            if step % 50 == 0:
                print(f'INT005 step {step}/{total_steps}: loss {np.mean(losses[-50:]):.4f}; '
                      f'{time.monotonic()-started:.1f}s', flush=True)
            if step % 500 == 0:
                model.save_pretrained(out)
                tokenizer.save_pretrained(out)
                if checkpoint_callback:
                    checkpoint_callback()
            if time.monotonic() - started >= max_seconds:
                stop = True
                break
        if stop:
            break
    model.save_pretrained(out)
    tokenizer.save_pretrained(out)
    report = {'initialization': MODEL, 'revision': REVISION, 'license': license_name,
              'parameters': parameter_count, 'fit_anchors': len(rows), 'steps': step,
              'planned_steps': total_steps, 'batch_size': batch_size, 'epochs_requested': epochs,
              'max_length': 128, 'temperature': .05, 'seed': 517,
              'seconds': time.monotonic()-started, 'stopped_on_time_budget': stop,
              'initial_loss_50': float(np.mean(losses[:50])),
              'final_loss_50': float(np.mean(losses[-50:])),
              'peak_gpu_bytes': torch.cuda.max_memory_allocated(),
              'note': 'Training loss only; no end-to-end retrieval or matching score established.'}
    (out / 'training_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
