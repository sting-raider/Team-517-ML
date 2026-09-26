"""Score competing v3 test owners with the frozen INT005 encoder."""
import gzip
import json
from pathlib import Path


def prepare(db, matching, out):
    import duckdb

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect(str(db), read_only=True)
    c.execute("SET memory_limit='12GB'")
    c.execute('SET threads=8')
    c.execute('''CREATE TEMP TABLE selected AS SELECT source1_entity_id AS owner,
        unnest(string_split(matched_entity_ids,',')) AS target
        FROM read_csv(?,delim='\t',header=true,all_varchar=true)
        WHERE matched_entity_ids<>'' ''', [str(matching)])
    c.execute('''CREATE TEMP TABLE conflicts AS SELECT target,count(*) owners
        FROM selected GROUP BY target HAVING count(*)>1''')
    c.execute('''CREATE TEMP TABLE conflict_pairs AS
        SELECT s.target,s.owner FROM selected s JOIN conflicts c USING(target)''')
    c.execute('''COPY (SELECT p.target,p.owner FROM conflict_pairs p)
        TO ? (FORMAT PARQUET)''', [str(out/'pairs.parquet')])
    c.execute('''COPY (SELECT t.entity_id,t.business_name,t.business_address
        FROM test t JOIN (SELECT target AS entity_id FROM conflict_pairs UNION
            SELECT owner AS entity_id FROM conflict_pairs) ids USING(entity_id))
        TO ? (FORMAT PARQUET)''', [str(out/'records.parquet')])
    summary = {country: {'targets': targets, 'edges': edges} for country,targets,edges in
               c.execute('''SELECT t.country,count(DISTINCT p.target),count(*)
                   FROM conflict_pairs p JOIN test t ON p.target=t.entity_id
                   GROUP BY 1''').fetchall()}
    report = {'conflict_targets': c.execute('SELECT count(*) FROM conflicts').fetchone()[0],
              'conflict_edges': c.execute('SELECT count(*) FROM conflict_pairs').fetchone()[0],
              'countries': summary,
              'protocol': 'Only target records with multiple predicted owners, identified without labels; full submitted v3 matching file'}
    (out/'prepare.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    c.close()
    return report


def score(root, encoder, margin=.05):
    import duckdb
    import numpy as np
    from .ownership import encode_records

    root = Path(root)
    c = duckdb.connect()
    records = c.execute('SELECT * FROM read_parquet(?)', [str(root/'records.parquet')]).fetchall()
    lookup, vectors = encode_records(records, encoder)
    pairs = c.execute('SELECT * FROM read_parquet(?) ORDER BY target,owner',
                      [str(root/'pairs.parquet')]).fetchall()
    groups = {}
    for target, owner in pairs:
        value = float(vectors[lookup[target]] @ vectors[lookup[owner]])
        groups.setdefault(target, []).append((owner,value))
    remove = []
    resolved = tied = 0
    for target, choices in groups.items():
        top = max(score for _,score in choices)
        winners = [owner for owner,value in choices if value >= top-margin-1e-7]
        if len(winners) == 1:
            resolved += 1
        else:
            tied += 1
        remove.extend((target,owner) for owner,value in choices if owner not in winners)
    c.execute('CREATE TEMP TABLE removed(target VARCHAR,owner VARCHAR)')
    c.executemany('INSERT INTO removed VALUES (?,?)', remove)
    c.execute('COPY removed TO ? (FORMAT PARQUET)', [str(root/'removed.parquet')])
    report = {'margin':margin,'conflict_targets':len(groups),'resolved_to_one':resolved,
              'retained_multiple':tied,'removed_edges':len(remove),
              'encoder':str(encoder),
              'protocol':'Keep owners within dense cosine margin of strongest selected owner; candidate set unchanged'}
    (root/'score.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def write_submission(matching, removed_parquet, out):
    import duckdb
    from .predict import sha256

    c = duckdb.connect()
    removed = {(target,owner) for target,owner in c.execute('SELECT * FROM read_parquet(?)',
                                                           [str(removed_parquet)]).fetchall()}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out/'matching_results.tsv'
    with Path(matching).open(encoding='utf-8',newline='') as src, \
         dest.open('w',encoding='utf-8',newline='') as dst:
        header = src.readline()
        if header.rstrip('\r\n') != 'source1_entity_id\tmatched_entity_ids':
            raise ValueError('Unexpected submitted matching header')
        dst.write(header)
        anchors = edges = kept = 0
        for line in src:
            owner,value = line.rstrip('\r\n').split('\t',1)
            targets = value.split(',') if value else []
            retain = [target for target in targets if (target,owner) not in removed]
            dst.write(f'{owner}\t{",".join(retain)}\n')
            anchors += 1
            edges += len(targets)
            kept += len(retain)
    if edges-kept != len(removed):
        raise ValueError('Some proposed removals were absent from matching file')
    report = {'anchors':anchors,'original_edges':edges,'retained_edges':kept,
              'removed_edges':len(removed),'matching_sha256':sha256(dest),
              'v3_matching_sha256':sha256(matching)}
    (out/'completion.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with dest.open('rb') as source,(out/'matching_results.tsv.gz').open('wb') as target:
        with gzip.GzipFile(filename='',mode='wb',fileobj=target,compresslevel=3,mtime=0) as zipped:
            for chunk in iter(lambda:source.read(1<<20),b''):
                zipped.write(chunk)
    report['compressed_sha256'] = sha256(out/'matching_results.tsv.gz')
    (out/'completion.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
