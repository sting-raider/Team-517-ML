"""Streaming output validation with optional disk-backed ID checks."""
import argparse
from pathlib import Path
from .data import connect
from .output_receipt import add_country_row, new_country_counts, ordered_country_counts


def parse(line,expected):
    columns=line.rstrip('\r\n').split('\t')
    if len(columns)!=2 or columns[0]!=expected:
        raise ValueError(f'Expected exactly one row for {expected} in sorted S1 order')
    ids=columns[1].split(',') if columns[1] else []
    if len(ids)!=len(set(ids)):
        raise ValueError(f'Duplicate target IDs under {expected}')
    if any(not i.startswith(('S2-','S3-')) or i!=i.strip() for i in ids):
        raise ValueError(f'Invalid target format under {expected}')
    return set(ids)


def validate(db,output,check_ids=True):
    c=connect(db)
    c.execute('SELECT entity_id,country FROM test WHERE source=1 ORDER BY entity_id')
    count=pairs=matches=empty=0
    countries=new_country_counts()
    with (output/'matching_results.tsv').open(encoding='utf-8') as mf, (output/'candidate_pairs.tsv').open(encoding='utf-8') as cf:
        if mf.readline().rstrip('\r\n')!='source1_entity_id\tmatched_entity_ids':
            raise ValueError('Wrong matching header')
        if cf.readline().rstrip('\r\n')!='source1_entity_id\tcandidate_entity_ids':
            raise ValueError('Wrong candidate header')
        while rows:=c.fetchmany(10000):
            for anchor,country in rows:
                predicted=parse(mf.readline(),anchor)
                candidates=parse(cf.readline(),anchor)
                if not predicted<=candidates:
                    raise ValueError(f'Prediction outside candidate set: {anchor}')
                count+=1
                pairs+=len(candidates)
                matches+=len(predicted)
                empty+=not predicted
                add_country_row(countries,country,candidates,predicted)
        if mf.readline() or cf.readline():
            raise ValueError('Extra rows in output')
    if check_ids:
        unknown=c.execute("""SELECT count(*) FROM (
            SELECT DISTINCT unnest(string_split(candidate_entity_ids,',')) AS target
            FROM read_csv(?,delim='\t',header=true,all_varchar=true)
            WHERE candidate_entity_ids IS NOT NULL) p
            ANTI JOIN test t ON p.target=t.entity_id AND t.source>1 WHERE target<>''""",
            [str((output/'candidate_pairs.tsv').resolve())]).fetchone()[0]
        if unknown:
            raise ValueError(f'{unknown} nonexistent target IDs')
    c.close()
    return {'anchors':count,'candidates':pairs,'matches':matches,
            'empty_predictions':empty,'target_ids_checked':check_ids,
            'status':'PASS','countries':ordered_country_counts(countries)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=Path('artifacts/data.duckdb'))
    p.add_argument('--output',type=Path,default=Path('output/baseline'))
    p.add_argument('--skip-id-check',action='store_true')
    a=p.parse_args()
    print(validate(a.db,a.output,not a.skip_id_check))


if __name__=='__main__':
    main()
