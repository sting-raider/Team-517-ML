"""Aggregate prediction counts by country without using hidden labels."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_country(path):
    with path.open(encoding='utf-8',newline='') as stream:
        rows=csv.DictReader(stream,delimiter='\t')
        return {row['entity_id']:row['country'] for row in rows}


def prediction_counts(path):
    with path.open(encoding='utf-8',newline='') as stream:
        rows=csv.DictReader(stream,delimiter='\t')
        if rows.fieldnames!=['source1_entity_id','matched_entity_ids']:
            raise ValueError(f'Unexpected matching schema: {path}')
        for row in rows:
            matches=row['matched_entity_ids']
            yield row['source1_entity_id'],0 if not matches else 1+matches.count(',')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source1',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--new',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    country=read_country(args.source1)
    counts=defaultdict(lambda: {'entities':0,'baseline_empty':0,'new_empty':0,
                                'baseline_matches':0,'new_matches':0,'changed_cardinality':0})
    seen=set()
    for (left,old),(right,new) in zip(prediction_counts(args.baseline),prediction_counts(args.new),strict=True):
        if left!=right or left not in country or left in seen:
            raise ValueError('Matching files do not align with unique Source 1 IDs')
        seen.add(left)
        row=counts[country[left]]
        row['entities']+=1
        row['baseline_empty']+=old==0
        row['new_empty']+=new==0
        row['baseline_matches']+=old
        row['new_matches']+=new
        row['changed_cardinality']+=old!=new
    if len(seen)!=len(country):
        raise ValueError('Matching files are incomplete')
    result={'protocol':'Unlabeled test country/cardinality drift only; no score estimate',
            'countries':{name:{**value,
                'baseline_mean_matches':value['baseline_matches']/value['entities'],
                'new_mean_matches':value['new_matches']/value['entities']}
                for name,value in sorted(counts.items())}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
