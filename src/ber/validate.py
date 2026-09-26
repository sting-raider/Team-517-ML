"""Streaming output validation with optional disk-backed ID checks."""
import argparse
from pathlib import Path
from .data import connect


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


def validate(db,output,check_ids=True,max_candidates_per_anchor=None):
    if max_candidates_per_anchor is not None and max_candidates_per_anchor<1:
        raise ValueError('max_candidates_per_anchor must be at least 1')
    c=connect(db)
    c.execute('SELECT entity_id FROM test WHERE source=1 ORDER BY entity_id')
    count=pairs=matches=empty=max_candidates_observed=0
    with (output/'matching_results.tsv').open(encoding='utf-8') as mf, (output/'candidate_pairs.tsv').open(encoding='utf-8') as cf:
        if mf.readline().rstrip('\r\n')!='source1_entity_id\tmatched_entity_ids':
            raise ValueError('Wrong matching header')
        if cf.readline().rstrip('\r\n')!='source1_entity_id\tcandidate_entity_ids':
            raise ValueError('Wrong candidate header')
        while rows:=c.fetchmany(10000):
            for (anchor,) in rows:
                predicted=parse(mf.readline(),anchor)
                candidates=parse(cf.readline(),anchor)
                candidate_count=len(candidates)
                if max_candidates_per_anchor is not None and candidate_count>max_candidates_per_anchor:
                    raise ValueError(f'Candidate cap exceeded under {anchor}: {candidate_count} > {max_candidates_per_anchor}')
                if not predicted<=candidates:
                    raise ValueError(f'Prediction outside candidate set: {anchor}')
                count+=1
                pairs+=candidate_count
                max_candidates_observed=max(max_candidates_observed,candidate_count)
                matches+=len(predicted)
                empty+=not predicted
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
    return {'anchors':count,'candidates':pairs,'matches':matches,'empty_predictions':empty,
            'max_candidates_observed':max_candidates_observed,
            'max_candidates_allowed':max_candidates_per_anchor,
            'target_ids_checked':check_ids,'status':'PASS'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',type=Path,default=Path('artifacts/data.duckdb'))
    p.add_argument('--output',type=Path,default=Path('output/baseline'))
    p.add_argument('--skip-id-check',action='store_true')
    p.add_argument('--max-candidates-per-anchor',type=int)
    a=p.parse_args()
    print(validate(a.db,a.output,not a.skip_id_check,a.max_candidates_per_anchor))


if __name__=='__main__':
    main()
