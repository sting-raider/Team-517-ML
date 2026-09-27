"""Aggregate exact pinned-tokenizer truncation audit on supplied test text.

The sample is deterministic by Source 1 ID hash. The first predicted target is
used only to form plausible test pairs; no accuracy label is inferred.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


PAIR_MODEL = 'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1'
PAIR_REVISION = '1427fd652930e4ba29e8149678df786c240d8825'
DENSE_MODEL = 'intfloat/multilingual-e5-small'
DENSE_REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'


def run_dense(db, per_country=5000):
    import duckdb
    import numpy as np
    from transformers import AutoTokenizer
    from ber.dense_training import serialize

    c = duckdb.connect(str(db), read_only=True)
    rows = c.execute('''SELECT country,business_name,business_address
        FROM test WHERE source=1 AND hash(entity_id)%100<2
        ORDER BY hash(entity_id)''').fetchall()
    c.close()
    selected = {country: [] for country in ('US','India','France')}
    for country, name, address in rows:
        if len(selected[country]) < per_country:
            selected[country].append(serialize(name, address))
    tokenizer = AutoTokenizer.from_pretrained(DENSE_MODEL,
                                               revision=DENSE_REVISION)
    result = {'model':DENSE_MODEL,'revision':DENSE_REVISION,
              'max_length':128,
              'sample_rule':'hash(Source1 ID)%100<2; max N per country',
              'countries':{}}
    for country, items in selected.items():
        lengths = []
        for start in range(0,len(items),100):
            encoded = tokenizer(items[start:start+100],truncation=False,
                                padding=False)
            lengths.extend(map(len,encoded['input_ids']))
        values = np.asarray(lengths)
        result['countries'][country] = {
            'records':len(values),
            'p99':float(np.percentile(values,99)),
            'max':int(values.max()),
            'over_128':int(np.count_nonzero(values>128))}
    return result


def run(db, matching, per_country=5000, candidate=None):
    import duckdb
    import numpy as np
    from transformers import AutoTokenizer
    from ber.dense_training import serialize

    c = duckdb.connect(str(db), read_only=True)
    c.execute('SET threads=8')
    if candidate is None:
        sample = '''
        WITH m AS (
            SELECT source1_entity_id anchor,
                   split_part(matched_entity_ids, ',', 1) target_id
            FROM read_csv(?, delim='\t', header=true,
                columns={'source1_entity_id':'VARCHAR',
                         'matched_entity_ids':'VARCHAR'})
            WHERE hash(source1_entity_id)%100 < 2
              AND matched_entity_ids <> ''
        )'''
        input_path = matching
        sample_rule = 'hash(Source1 ID)%100<2; first V6 predicted target'
    else:
        sample = '''
        WITH sampled_anchors AS (
            SELECT source1_entity_id anchor,candidate_entity_ids
            FROM read_csv(?, delim='\t', header=true,
                columns={'source1_entity_id':'VARCHAR',
                         'candidate_entity_ids':'VARCHAR'})
            WHERE hash(source1_entity_id)%100 < 2
        ), m AS (
            SELECT anchor,unnest(string_split(candidate_entity_ids, ',')) target_id
            FROM sampled_anchors
        )'''
        input_path = candidate
        sample_rule = 'hash(Source1 ID)%100<2; hash(pair)%20=0 among all frozen candidates'
    pair_filter = '' if candidate is None else \
        "WHERE hash(m.anchor || ':' || m.target_id)%20=0"
    rows = c.execute(sample + '''
        SELECT a.country,a.business_name,a.business_address,
               t.business_name,t.business_address
        FROM m JOIN test a ON m.anchor=a.entity_id
        JOIN test t ON m.target_id=t.entity_id
        ''' + pair_filter + '''
        ORDER BY hash(m.anchor)
    ''', [str(input_path)]).fetchall()
    c.close()
    selected = defaultdict(list)
    for country, an, aa, tn, ta in rows:
        if len(selected[country]) < per_country:
            selected[country].append((serialize(an, aa), serialize(tn, ta)))
    tokenizer = AutoTokenizer.from_pretrained(PAIR_MODEL,
                                               revision=PAIR_REVISION)
    result = {'model': PAIR_MODEL, 'revision': PAIR_REVISION,
              'max_length': 160, 'sample_rule':sample_rule +
              '; max N per country',
              'countries': {}}
    for country, pairs in selected.items():
        lengths = []
        for start in range(0, len(pairs), 100):
            batch = pairs[start:start+100]
            encoded = tokenizer([x for x,_ in batch],
                                [y for _,y in batch],
                                truncation=False, padding=False)
            lengths.extend(map(len, encoded['input_ids']))
        values = np.asarray(lengths)
        result['countries'][country] = {
            'pairs': len(values),
            'p50': float(np.percentile(values, 50)),
            'p90': float(np.percentile(values, 90)),
            'p99': float(np.percentile(values, 99)),
            'max': int(values.max()),
            'over_160': int(np.count_nonzero(values > 160)),
            'over_160_rate': float(np.mean(values > 160))}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--matching', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--dense', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--per-country', type=int, default=5000)
    args = parser.parse_args()
    if args.dense:
        report = run_dense(args.db,args.per_country)
    else:
        if args.matching is None:
            parser.error('--matching is required for pair audits')
        report = run(args.db, args.matching, args.per_country,args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
