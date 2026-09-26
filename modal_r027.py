"""R027: diagnose and test number-gated character retrieval."""
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import modal
from modal_app import image, volume, VOLUME_ROOT, SCRATCH, _enable_native_features

image = image.add_local_python_source('modal_app')
app = modal.App('team517-r027-number-char')
ROOT = VOLUME_ROOT / 'project/experiments/r027'
DB = VOLUME_ROOT / 'project/artifacts/data_v3.duckdb'


def copy_database():
    path = SCRATCH / 'artifacts/r027.duckdb'
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DB, path)
    return path


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, timeout=600)
def index_sizing():
    from ber.data import connect
    c = connect(copy_database())
    c.execute('SET threads=8')
    postings = c.execute('SELECT count(*) FROM train_char_index').fetchone()[0]
    rows = c.execute('''SELECT count(*) records,
        sum(len(list_distinct(regexp_extract_all(a,'[0-9]+')))) number_memberships,
        avg(len(list_distinct(regexp_extract_all(a,'[0-9]+')))) mean_numbers,
        count(*) FILTER (WHERE regexp_extract(a,'[0-9]+')<>'') with_number
        FROM train WHERE source>1''').fetchone()
    c.close()
    return {'character_postings': postings, 'records': rows[0],
            'number_memberships': rows[1], 'mean_numbers': rows[2],
            'records_with_number': rows[3]}


def select_calibration(c):
    from ber.experiment import fold
    c.execute('''CREATE OR REPLACE TEMP TABLE r027_dev30k AS SELECT * FROM train
        WHERE source=1 ORDER BY md5('sample517:'||entity_id) LIMIT 30000''')
    ids = [(i,) for (i,) in c.execute('SELECT entity_id FROM r027_dev30k').fetchall()
           if fold(i) == 'calibrate']
    c.execute('CREATE OR REPLACE TEMP TABLE r027_ids(entity_id VARCHAR)')
    c.executemany('INSERT INTO r027_ids VALUES (?)', ids)
    c.execute('''CREATE OR REPLACE TEMP TABLE r027_anchors AS SELECT d.*
        FROM r027_dev30k d JOIN r027_ids USING(entity_id)''')
    if len(ids) != 4389:
        raise ValueError(f'Unexpected calibration size: {len(ids)}')
    return ids


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, timeout=1800)
def diagnose():
    from ber.data import connect
    from ber.blocking import build_index
    from ber.retrieval_v3 import build_char_index, fused_candidates
    from rapidfuzz import fuzz

    c = connect(copy_database())
    c.execute("SET memory_limit='20GB'")
    c.execute('SET threads=8')
    build_index(c, 'train')
    build_char_index(c, 'train')
    select_calibration(c)
    fused_candidates(c, 'train', 'r027_anchors', 'r027_fused', 160)
    total = c.execute('''SELECT count(*) FROM edges e
        JOIN r027_anchors l ON l.entity_id=e.anchor''').fetchone()[0]
    missed = c.execute('''SELECT l.n,l.a,r.n,r.a,r.source,
        bl.rid IS NOT NULL AS in_lexical, ch.rid IS NOT NULL AS in_character
        FROM edges e JOIN r027_anchors l ON l.entity_id=e.anchor
        JOIN train r ON r.entity_id=e.target
        LEFT JOIN fusion_lexical bl ON bl.anchor=e.anchor AND bl.rid=r.rowid
        LEFT JOIN fusion_character ch ON ch.anchor=e.anchor AND ch.rid=r.rowid
        ANTI JOIN r027_fused p ON p.anchor=e.anchor AND p.rid=r.rowid''').fetchall()
    count = Counter()
    for n1, a1, n2, a2, source, in_lexical, in_character in missed:
        nt1, nt2 = set(n1.split()), set(n2.split())
        at1, at2 = set(a1.split()), set(a2.split())
        aw1 = {t for t in at1 if len(t) >= 3 and not t.isdigit()}
        aw2 = {t for t in at2 if len(t) >= 3 and not t.isdigit()}
        d1, d2 = re.findall(r'\d+', a1), re.findall(r'\d+', a2)
        same_first = bool(d1 and d2 and d1[0] == d2[0])
        same_any = bool(set(d1) & set(d2))
        name_exact = bool(nt1 & nt2)
        address_exact = bool(at1 & at2)
        count['missed'] += 1
        count[f'source_{source}'] += 1
        for flag, key in ((same_first, 'same_first_address_number'),
                          (same_any, 'some_shared_address_number'),
                          (name_exact, 'some_exact_name_token'),
                          (address_exact, 'some_exact_address_token'),
                          (bool(aw1 & aw2), 'some_exact_address_word'),
                          (same_first and not aw1 & aw2, 'same_number_no_address_word'),
                          (same_first and not name_exact, 'same_number_no_name_token'),
                          (not name_exact and not address_exact, 'no_exact_tokens'),
                          (in_lexical, 'inside_lexical160_but_pruned'),
                          (in_character, 'inside_char64_but_pruned'),
                          (in_lexical or in_character, 'inside_union_but_pruned'),
                          (fuzz.ratio(a1, a2) >= 70, 'address_ratio_at_least_70'),
                          (fuzz.ratio(n1, n2) >= 70, 'name_ratio_at_least_70')):
            if flag:
                count[key] += 1
    report = {'calibration_anchors': 4389, 'positive_pairs': total,
              'missed_positive_pairs': len(missed),
              'pair_recall': 1 - len(missed) / total,
              'missed_pair_categories': dict(count)}
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'diagnosis.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    volume.commit()
    return report


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8,
              memory=32768, timeout=1800)
def retrieval_gate(any_number: bool = False):
    _enable_native_features()
    from ber.data import connect
    from ber.blocking import build_index
    from ber.retrieval_v3 import build_char_index, fused_candidates, evaluate_table
    from ber.v2 import frequency_tables
    from ber.predict import score_batch
    from ber.metrics import evaluate
    from catboost import CatBoostClassifier
    from concurrent.futures import ProcessPoolExecutor

    c = connect(copy_database())
    c.execute("SET memory_limit='20GB'")
    c.execute('SET threads=8')
    build_index(c, 'train')
    build_char_index(c, 'train')
    select_calibration(c)
    meta = [{'id': i, 'country': co, 'truth': truth.split(',') if truth else []}
            for i, co, truth in c.execute('''SELECT a.entity_id,a.country,t.matches
              FROM r027_anchors a JOIN truth t ON a.entity_id=t.anchor''').fetchall()]
    fused_candidates(c, 'train', 'r027_anchors', 'r027_fused', 160)
    baseline = evaluate_table(c, 'r027_fused', meta)

    # Reuse the existing bounded name-character postings, but condition on the
    # anchor's first address number before ranking. This is an indexable key if
    # the full-data gate warrants building a dedicated composite index.
    number_condition = (
        "list_has_any(regexp_extract_all(a.a,'[0-9]+'),regexp_extract_all(t.a,'[0-9]+'))"
        if any_number else
        "regexp_extract(a.a,'[0-9]+')<>'' AND regexp_extract(a.a,'[0-9]+')=regexp_extract(t.a,'[0-9]+')"
    )
    c.execute(f'''CREATE OR REPLACE TEMP TABLE r027_number_char AS
        WITH hits AS (
          SELECT q.anchor,r.rid,sum(ln(10000001.0/r.freq))::FLOAT retrieval,
                 count(*)::SMALLINT hits
          FROM char_query q JOIN train_char_index r USING(key)
          JOIN r027_anchors a ON a.entity_id=q.anchor
          JOIN train t ON t.rowid=r.rid
          WHERE {number_condition}
          GROUP BY q.anchor,r.rid HAVING count(*)>=2)
        SELECT h.* FROM hits h JOIN train t ON t.rowid=h.rid
        QUALIFY row_number() OVER(PARTITION BY h.anchor
            ORDER BY h.retrieval DESC,t.entity_id)<=32''')
    raw_count = c.execute('SELECT count(*) FROM r027_number_char').fetchone()[0]
    c.execute('''CREATE OR REPLACE TEMP TABLE r027_union AS
        SELECT anchor,rid FROM r027_fused
        UNION SELECT anchor,rid FROM r027_number_char''')
    union = evaluate_table(c, 'r027_union', meta)
    c.execute('''CREATE OR REPLACE TEMP TABLE r027_fused160 AS
        WITH weighted AS (
          SELECT anchor,rid,retrieval::FLOAT weight FROM r027_fused
          UNION ALL
          SELECT anchor,rid,(0.5/(60+rank() OVER(PARTITION BY anchor
                 ORDER BY retrieval DESC)))::FLOAT weight
          FROM r027_number_char), scored AS (
          SELECT anchor,rid,sum(weight)::FLOAT retrieval
          FROM weighted GROUP BY anchor,rid)
        SELECT s.anchor,s.rid,s.retrieval,
          (coalesce(b.base_hits,0)+greatest(coalesce(b.char_hits,0),coalesce(n.hits,0)))::SMALLINT hits,
          coalesce(b.base_retrieval,0)::FLOAT base_retrieval,
          greatest(coalesce(b.char_retrieval,0),coalesce(n.retrieval,0))::FLOAT char_retrieval,
          coalesce(b.base_hits,0)::SMALLINT base_hits,
          greatest(coalesce(b.char_hits,0),coalesce(n.hits,0))::SMALLINT char_hits
        FROM scored s JOIN train t ON t.rowid=s.rid
        LEFT JOIN r027_fused b ON b.anchor=s.anchor AND b.rid=s.rid
        LEFT JOIN r027_number_char n ON n.anchor=s.anchor AND n.rid=s.rid
        QUALIFY row_number() OVER(PARTITION BY s.anchor
            ORDER BY s.retrieval DESC,t.entity_id)<=160''')
    capped = evaluate_table(c, 'r027_fused160', meta)
    frequency_tables(c, 'train')
    model = CatBoostClassifier()
    model.load_model(str(VOLUME_ROOT / 'project/experiments/int003/depth10/mixed.cbm'))
    with ProcessPoolExecutor(max_workers=8) as workers:
        old_pred, _ = score_batch(c, model, .625, 'train', 'r027_anchors',
                                  'r027_fused', 160, workers, 3)
        new_pred, _ = score_batch(c, model, .625, 'train', 'r027_anchors',
                                  'r027_fused160', 160, workers, 3)
    truth = {m['id']: m['truth'] for m in meta}
    matcher = {'baseline': evaluate(truth, old_pred),
               'number_char': evaluate(truth, new_pred)}
    report = {'protocol': 'Same 4389 calibration anchors; full train inventory; v3 cap160 plus address-number-conditioned name-char top32; no labels in retrieval',
              'number_rule': 'any_shared_address_number' if any_number else 'same_first_address_number',
              'number_char_pairs': raw_count, 'baseline': baseline,
              'union': union, 'fused160': capped,
              'frozen_v3_matcher': matcher,
              'oracle_delta': capped['blocking_oracle_macro_f0_5'] - baseline['blocking_oracle_macro_f0_5'],
              'pair_recall_delta': capped['candidate_pair_recall'] - baseline['candidate_pair_recall']}
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / ('retrieval_any_number.json' if any_number else 'retrieval_gate.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    volume.commit()
    return report


@app.local_entrypoint()
def main(action: str = 'diagnose'):
    if action == 'diagnose':
        report = diagnose.remote()
        output = Path('reports/r027_diagnosis.json')
    elif action in ('retrieval', 'retrieval-any'):
        report = retrieval_gate.remote(action == 'retrieval-any')
        output = Path('reports/r027_retrieval_any.json' if action == 'retrieval-any' else 'reports/r027_retrieval.json')
    elif action == 'size':
        report = index_sizing.remote()
        output = Path('reports/r027_index_sizing.json')
    else:
        raise ValueError('Unknown action')
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
