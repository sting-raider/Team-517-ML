"""Disk-backed input preparation and integrity audit. No external data access."""
import argparse
import json
import time
from pathlib import Path

import duckdb


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


def prepare(data, db, report):
    db.parent.mkdir(parents=True, exist_ok=True)
    con = connect(db)
    con.execute(r"""CREATE OR REPLACE MACRO norm(s) AS
        trim(regexp_replace(lower(strip_accents(coalesce(s, ''))), '[^\p{L}\p{N}]+', ' ', 'g'))""")
    for split in ('train', 'test'):
        exists = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name=?", [split]).fetchone()[0]
        existing_sources = {r[0] for r in con.execute(f'SELECT DISTINCT source FROM {split}').fetchall()} if exists else set()
        if existing_sources == {1,2,3}:
            print(f'Reusing {split} table', flush=True)
            continue
        for source in (1, 2, 3):
            if source in existing_sources:
                continue
            path = str((data / split / f'{split}_source{source}.tsv').resolve())
            start = time.time()
            action = f'CREATE TABLE {split} AS' if source == 1 else f'INSERT INTO {split}'
            con.execute(f"""{action} SELECT entity_id, coalesce(business_name,'') AS business_name,
                coalesce(business_address,'') AS business_address, coalesce(country,'') AS country,
                {source} AS source, norm(business_name) AS n, norm(business_address) AS a
                FROM read_csv(?, delim='\t', header=true, all_varchar=true)""", [path])
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
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    con.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--db', type=Path, default=Path('artifacts/data.duckdb'))
    p.add_argument('--report', type=Path, default=Path('reports/data_audit.json'))
    args = p.parse_args()
    prepare(args.data, args.db, args.report)


if __name__ == '__main__':
    main()
