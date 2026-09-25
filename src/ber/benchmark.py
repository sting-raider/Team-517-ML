"""Deterministic fixed-slice retrieval benchmark for swarm experiments.

The default is the established 30k development sample restricted to the calibration
fold. It intentionally does not touch the separate confirmation sample.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

SAMPLE_SALT = 'sample517:'
FOLD_SALT = 'fold517:'
DEFAULT_SAMPLE_SIZE = 30000
DEFAULT_CAP = 640


def anchor_fold(entity_id):
    """Mirror the established experiment fold assignment without loading model code."""
    bucket = int(hashlib.sha256((FOLD_SALT + entity_id).encode()).hexdigest()[:8], 16) % 100
    return 'fit' if bucket < 60 else 'early' if bucket < 75 else 'calibrate' if bucket < 90 else 'holdout'


def candidate_count_stats(truth, candidates):
    counts = sorted(len(candidates.get(k, ())) for k in truth)
    if not counts:
        raise ValueError('Cannot summarize an empty evaluation set')

    def quantile(q):
        if len(counts) == 1:
            return float(counts[0])
        pos = (len(counts) - 1) * q
        lo = int(pos)
        hi = min(lo + 1, len(counts) - 1)
        frac = pos - lo
        return float(counts[lo] * (1 - frac) + counts[hi] * frac)

    return {
        'total': int(sum(counts)),
        'mean': float(sum(counts) / len(counts)),
        'p50': quantile(.50),
        'p90': quantile(.90),
        'p99': quantile(.99),
        'max': float(counts[-1]),
    }


def filter_mapping(mapping, keys):
    keys = set(keys)
    return {k: mapping[k] for k in mapping if k in keys}


def filter_targets(mapping, target_source, source):
    return {k: {t for t in values if target_source.get(t) == source} for k, values in mapping.items()}


def retrieval_metrics(truth, candidates):
    from .metrics import evaluate

    result = evaluate(truth, {}, candidates)
    result.pop('macro_f0_5', None)
    result.pop('singleton_false_positive_rate', None)
    # Keep the official evaluate() quantiles and add total/mean for candidate-budget comparisons.
    result['candidate_counts'] = candidate_count_stats(truth, candidates)
    return result


def select_anchor_ids(con, sample_size=DEFAULT_SAMPLE_SIZE, fold='calibrate'):
    if sample_size <= 0:
        raise ValueError('sample_size must be positive')
    rows = con.execute(
        f"""SELECT entity_id FROM train WHERE source=1
        ORDER BY md5('{SAMPLE_SALT}' || entity_id) LIMIT {int(sample_size)}"""
    ).fetchall()
    selected = [entity_id for (entity_id,) in rows if anchor_fold(entity_id) == fold]
    if not selected:
        raise ValueError(f'No anchors selected for fold={fold!r} from sample_size={sample_size}')
    return selected


def summarize(con, anchor_table='benchmark_anchors', candidate_table='benchmark_candidates'):
    anchor_rows = con.execute(
        f"""SELECT a.entity_id,a.country,g.matches
        FROM {anchor_table} a JOIN truth g ON a.entity_id=g.anchor ORDER BY a.entity_id"""
    ).fetchall()
    truth = {
        anchor: set(matches.split(',')) if matches else set()
        for anchor, _country, matches in anchor_rows
    }
    countries = {anchor: country for anchor, country, _matches in anchor_rows}
    if not truth:
        raise ValueError('Benchmark anchor table has no labeled anchors')

    candidates = {anchor: set() for anchor in truth}
    candidate_source = {2: {anchor: set() for anchor in truth}, 3: {anchor: set() for anchor in truth}}
    for anchor, target, source in con.execute(
        f"""SELECT p.anchor,r.entity_id,r.source FROM {candidate_table} p
        JOIN train r ON p.rid=r.rowid ORDER BY p.anchor,r.entity_id"""
    ).fetchall():
        if anchor not in candidates:
            raise ValueError(f'Candidate table contains anchor outside benchmark slice: {anchor}')
        candidates[anchor].add(target)
        if source in candidate_source:
            candidate_source[source][anchor].add(target)

    target_source = dict(con.execute(
        f"""SELECT e.target,r.source FROM edges e
        JOIN {anchor_table} a ON e.anchor=a.entity_id
        JOIN train r ON e.target=r.entity_id AND r.source IN (2,3)"""
    ).fetchall())

    overall = retrieval_metrics(truth, candidates)
    country_slices = {}
    for country in sorted(set(countries.values())):
        keys = [k for k, value in countries.items() if value == country]
        country_slices[country] = retrieval_metrics(
            filter_mapping(truth, keys), filter_mapping(candidates, keys)
        )

    source_slices = {}
    for source in (2, 3):
        source_truth = filter_targets(truth, target_source, source)
        source_slices[f'source{source}'] = retrieval_metrics(source_truth, candidate_source[source])

    return {
        'overall': overall,
        'country_slices': country_slices,
        'target_source_slices': source_slices,
    }


def run(db, report, sample_size=DEFAULT_SAMPLE_SIZE, cap=DEFAULT_CAP, fold='calibrate', allow_holdout=False):
    if fold == 'holdout' and not allow_holdout:
        raise ValueError('Development holdout is guarded; pass --allow-holdout explicitly')
    if fold not in {'calibrate', 'holdout'}:
        raise ValueError('benchmark fold must be calibrate or holdout')
    if cap <= 0:
        raise ValueError('cap must be positive')

    from .blocking import build_index, candidates as generate_candidates
    from .data import connect

    started = time.time()
    con = connect(db)
    try:
        selected = select_anchor_ids(con, sample_size, fold)
        con.execute('CREATE OR REPLACE TEMP TABLE benchmark_selection(id VARCHAR PRIMARY KEY)')
        con.executemany('INSERT INTO benchmark_selection VALUES (?)', [(x,) for x in selected])
        con.execute('''CREATE OR REPLACE TEMP TABLE benchmark_anchors AS
            SELECT t.* FROM train t JOIN benchmark_selection s ON t.entity_id=s.id
            WHERE t.source=1''')

        index_started = time.time()
        build_index(con, 'train')
        index_seconds = time.time() - index_started
        index_version_row = con.execute(
            "SELECT version FROM index_versions WHERE split='train'"
        ).fetchone()

        candidate_started = time.time()
        generate_candidates(con, 'train', 'benchmark_anchors', 'benchmark_candidates', cap)
        candidate_seconds = time.time() - candidate_started

        metric_started = time.time()
        result = summarize(con)
        metric_seconds = time.time() - metric_started
        selection_sha256 = hashlib.sha256(('
'.join(sorted(selected)) + '
').encode()).hexdigest()
        result.update({
            'protocol': {
                'sample': f"source1 ORDER BY md5('{SAMPLE_SALT}' || entity_id) LIMIT {sample_size}",
                'fold': fold,
                'fold_salt': FOLD_SALT,
                'labels': 'train truth only; confirmation sample excluded',
                'candidate_generator': 'blocker v2 via ber.blocking',
                'candidate_cap': int(cap),
                'retrieval_index_version': int(index_version_row[0]) if index_version_row else None,
                'selection_sha256': selection_sha256,
                'reference': 'reports/retrieval_study.json:retrieval_640' if sample_size == 30000 and fold == 'calibrate' and cap == 640 else None,
            },
            'anchors_selected': len(selected),
            'runtime_seconds': {
                'index_build_or_reuse': index_seconds,
                'candidate_generation': candidate_seconds,
                'metrics': metric_seconds,
                'total': time.time() - started,
            },
        })
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2, sort_keys=True), encoding='utf-8')
        return result
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path('artifacts/data.duckdb'))
    parser.add_argument('--report', type=Path, default=Path('reports/benchmark.json'))
    parser.add_argument('--anchors', type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument('--cap', type=int, default=DEFAULT_CAP)
    parser.add_argument('--fold', choices=['calibrate', 'holdout'], default='calibrate')
    parser.add_argument('--allow-holdout', action='store_true',
                        help='Required to evaluate the repeatedly inspected development holdout')
    args = parser.parse_args()
    result = run(args.db, args.report, args.anchors, args.cap, args.fold, args.allow_holdout)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
