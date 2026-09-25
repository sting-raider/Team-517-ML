"""Disk-backed input preparation and integrity audit. No external data access."""
import argparse
import inspect
import json
import time
from pathlib import Path

import duckdb

from .provenance import StaleArtifactError, file_signature, fingerprint


DATA_PREP_VERSION=1
NORM_MACRO_SQL=r"""CREATE OR REPLACE MACRO norm(s) AS
    trim(regexp_replace(lower(strip_accents(coalesce(s, ''))), '[^\p{L}\p{N}]+', ' ', 'g'))"""


def connect(path):
    con = duckdb.connect(str(path))
    con.execute("SET memory_limit='4GB'")
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    return con


def rows(con, sql):
    result = con.execute(sql)
    names = [x[0] for x in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def load_source(con, split, source, path, action):
    """Import one supplied source file using the canonical prepared-table schema."""
    con.execute(f"""{action} SELECT entity_id, coalesce(business_name,'') AS business_name,
        coalesce(business_address,'') AS business_address, coalesce(country,'') AS country,
        {source} AS source, norm(business_name) AS n, norm(business_address) AS a
        FROM read_csv(?, delim='\t', header=true, all_varchar=true)""", [str(path)])


def prep_contract_fingerprint():
    """Fingerprint preprocessing behavior that determines persisted train/test rows."""
    return fingerprint({
        'version':DATA_PREP_VERSION,
        'normalization_sql':NORM_MACRO_SQL,
        'load_source':inspect.getsource(load_source),
    })


def split_input_identity(data, split):
    """Cheap identity for the three raw files plus preprocessing contract."""
    files={}
    for source in (1,2,3):
        path=(data/split/f'{split}_source{source}.tsv').resolve()
        files[f'{split}_source{source}.tsv']=file_signature(path)
    return {
        'split':split,
        'prep_contract':prep_contract_fingerprint(),
        'files':files,
    }


def prepare(data, db, report, refresh=False):
    db.parent.mkdir(parents=True, exist_ok=True)
    con = connect(db)
    con.execute(NORM_MACRO_SQL)
    con.execute('''CREATE TABLE IF NOT EXISTS data_input_signatures (
        split VARCHAR PRIMARY KEY, fingerprint VARCHAR NOT NULL)''')
    for split in ('train', 'test'):
        identity=split_input_identity(data,split)
        current=fingerprint(identity)
        exists = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name=?", [split]).fetchone()[0]
        stored=con.execute('SELECT fingerprint FROM data_input_signatures WHERE split=?',[split]).fetchone()
        if exists and (not stored or stored[0]!=current):
            if not refresh:
                reason='unsigned legacy table' if not stored else f"stale input signature {stored[0][:12]} != {current[:12]}"
                con.close()
                raise StaleArtifactError(
                    f'{split} prepared table is an {reason}; rerun ber.data with --refresh '
                    'instead of silently reusing it'
                )
            con.execute(f'DROP TABLE {split}')
            exists=0
            stored=None
            print(f'Refresh requested: rebuilding {split} prepared table',flush=True)
        existing_sources = {r[0] for r in con.execute(f'SELECT DISTINCT source FROM {split}').fetchall()} if exists else set()
        if existing_sources == {1,2,3}:
            print(f'Reusing signed {split} table ({current[:12]})', flush=True)
            continue
        if existing_sources and not stored:
            con.close()
            raise StaleArtifactError(
                f'{split} is a partial unsigned legacy import; rerun ber.data with --refresh'
            )
        # Store the intended identity before import so an interrupted signed import can
        # resume source-by-source only when the same raw inputs and prep contract remain.
        con.execute('INSERT OR REPLACE INTO data_input_signatures VALUES (?,?)',[split,current])
        for source in (1, 2, 3):
            if source in existing_sources:
                continue
            path = (data / split / f'{split}_source{source}.tsv').resolve()
            start = time.time()
            action = f'CREATE TABLE {split} AS' if source == 1 and not exists else f'INSERT INTO {split}'
            load_source(con,split,source,path,action)
            exists=1
            con.execute('CHECKPOINT')
            print(f'Imported {split} source {source}: {time.time()-start:.1f}s', flush=True)
    con.execute("""CREATE OR REPLACE TABLE truth AS SELECT source1_entity_id AS anchor,
        coalesce(matched_entity_ids,'') AS matches FROM read_csv(?, delim='\t', header=true, all_varchar=true)""",
        [str((data / 'train/train_ground_truth.tsv').resolve())])
    con.execute("""CREATE OR REPLACE TABLE edges AS SELECT anchor, trim(unnest(string_split(matches,','))) AS target
        FROM truth WHERE matches <> ''""")
    result = {}
    for split in ('train', 'test'):
        result[split] = rows(con, f"""SELECT source, country, count(*) AS records,
            count(*)-count(DISTINCT entity_id) AS duplicate_ids,
            count(*) FILTER (WHERE n='') AS empty_names, count(*) FILTER (WHERE a='') AS empty_addresses,
            round(avg(length(business_name)),2) AS avg_name_length,
            round(avg(length(business_address)),2) AS avg_address_length
            FROM {split} GROUP BY source,country ORDER BY source,country""")
    result['cardinality'] = rows(con, """SELECT CASE WHEN matches='' THEN 0 ELSE len(string_split(matches,',')) END AS matches,
        count(*) AS anchors FROM truth GROUP BY ALL ORDER BY 1""")
    checks = {
        'duplicate_truth_anchors': 'SELECT count(*)-count(DISTINCT anchor) FROM truth',
        'duplicate_positive_pairs': 'SELECT count(*) FROM (SELECT anchor,target FROM edges GROUP BY ALL HAVING count(*)>1)',
        'targets_with_multiple_anchors': 'SELECT count(*) FROM (SELECT target FROM edges GROUP BY target HAVING count(DISTINCT anchor)>1)',
        'missing_truth_anchors': "SELECT count(*) FROM train t ANTI JOIN truth g ON t.entity_id=g.anchor WHERE source=1",
        'unknown_truth_anchors': "SELECT count(*) FROM truth g ANTI JOIN train t ON t.entity_id=g.anchor AND t.source=1",
        'unknown_truth_targets': "SELECT count(*) FROM edges e ANTI JOIN train t ON e.target=t.entity_id AND t.source IN (2,3)",
        'cross_country_positive_pairs': "SELECT count(*) FROM edges e JOIN train l ON l.entity_id=e.anchor JOIN train r ON r.entity_id=e.target WHERE l.country<>r.country",
    }
    result['integrity'] = {k: con.execute(v).fetchone()[0] for k,v in checks.items()}
    result['prepared_input_fingerprints']={
        split:con.execute('SELECT fingerprint FROM data_input_signatures WHERE split=?',[split]).fetchone()[0]
        for split in ('train','test')
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    con.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--db', type=Path, default=Path('artifacts/data.duckdb'))
    p.add_argument('--report', type=Path, default=Path('reports/data_audit.json'))
    p.add_argument('--refresh',action='store_true',
                   help='Rebuild prepared split tables when raw/preprocessing provenance changed')
    args = p.parse_args()
    prepare(args.data, args.db, args.report, args.refresh)


if __name__ == '__main__':
    main()
