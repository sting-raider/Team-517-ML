"""Evaluate legal-suffix/order recovery on frozen neural32 candidates."""

import json
import re
from collections import Counter

import duckdb
import numpy as np


ALIASES = {
    'private': 'pvt', 'limited': 'ltd', 'incorporated': 'inc',
    'corporation': 'corp', 'company': 'co', 'l': 'l',
}


def canonical(value):
    tokens = [ALIASES.get(word, word) for word in re.findall(r'\w+', value)]
    return ' '.join(sorted(tokens))


def metric(chosen, groups, truth, truth_count, anchors):
    use = np.isin(groups, anchors)
    g = groups[use]
    pred = chosen[use]
    tp = np.bincount(g, weights=pred & truth[use], minlength=len(truth_count))[anchors]
    pc = np.bincount(g, weights=pred, minlength=len(truth_count))[anchors]
    tc = truth_count[anchors]
    fp = pc - tp
    fn = tc - tp
    each = np.where(tc == 0, (pc == 0).astype(float),
                    1.25 * tp / np.maximum(1e-9, 1.25 * tp + fp + .25 * fn))
    return float(each.mean())


def main():
    with np.load('artifacts/capped_pairs/local_decisions.npz') as z:
        anchor = np.asarray(z['anchor'], str)
        target = np.asarray(z['target'], str)
        fold = np.asarray(z['fold'], str)
        truth = z['truth'].astype(bool)
        baseline = z['chosen'].astype(bool)
    ids = sorted(set(anchor) | set(target))
    db = duckdb.connect('artifacts/data.duckdb', read_only=True)
    db.execute('CREATE TEMP TABLE ids AS SELECT unnest(?) entity_id', [ids])
    records = {i: (c, n, a) for i, c, n, a in db.execute('''
        SELECT t.entity_id,t.country,t.n,t.a FROM train t JOIN ids USING(entity_id)
    ''').fetchall()}
    unique = set(db.execute('''SELECT country,n FROM train WHERE source=1 AND n<>''
        GROUP BY 1,2 HAVING count(*)=1''').fetchall())
    group_names = sorted(set(anchor))
    index = {x: i for i, x in enumerate(group_names)}
    groups = np.fromiter((index[x] for x in anchor), np.int32, count=len(anchor))
    db.execute('CREATE TEMP TABLE anchors AS SELECT unnest(?) anchor', [group_names])
    truth_count = np.zeros(len(group_names), np.int32)
    for a, count in db.execute('''SELECT e.anchor,count(*) FROM edges e JOIN anchors s
        USING(anchor) GROUP BY e.anchor''').fetchall():
        truth_count[index[a]] = count
    exact = np.zeros(len(anchor), bool)
    legal = np.zeros(len(anchor), bool)
    for i, (a, t) in enumerate(zip(anchor, target)):
        country, aname, _ = records[a]
        _, tname, taddr = records[t]
        if not aname or not tname or taddr or (country, aname) not in unique:
            continue
        exact[i] = aname == tname
        legal[i] = canonical(aname) == canonical(tname)
    recovered = baseline | exact
    expanded = recovered | legal
    report = {}
    for name, mask in [('calibrate', fold == 'calibrate'), ('holdout', fold == 'holdout')]:
        subset = np.unique(groups[mask])
        add = mask & legal & ~recovered
        report[name] = {
            'baseline': metric(baseline, groups, truth, truth_count, subset),
            'v6': metric(recovered, groups, truth, truth_count, subset),
            'expanded': metric(expanded, groups, truth, truth_count, subset),
            'added_true': int((add & truth).sum()),
            'added_false': int((add & ~truth).sum()),
            'added_country': dict(Counter(records[anchor[i]][0] for i in np.flatnonzero(add))),
        }
    print(json.dumps(report, indent=2))
    with open('reports/legal_blank_recovery_eval.json', 'w', encoding='utf-8') as out:
        json.dump(report, out, indent=2)


if __name__ == '__main__':
    main()
