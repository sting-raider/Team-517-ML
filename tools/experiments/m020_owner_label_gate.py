"""Labeled structural proxy for address-based resolution of competing owners."""
import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path


def run(db_path):
    import duckdb
    from rapidfuzz.fuzz import token_sort_ratio

    con = duckdb.connect(str(db_path), read_only=True)
    con.execute('SET threads=8')
    query = '''WITH names AS (
        SELECT country,n FROM train WHERE source=1 AND n<>''
        GROUP BY country,n HAVING count(*) BETWEEN 2 AND 20)
        SELECT r.entity_id,r.a,r.country,l.entity_id,l.a,
               e.anchor IS NOT NULL AS positive
        FROM train r JOIN names USING(country,n)
        JOIN train l ON l.source=1 AND l.country=r.country AND l.n=r.n
        LEFT JOIN edges e ON e.target=r.entity_id AND e.anchor=l.entity_id
        WHERE r.source IN(2,3) ORDER BY r.entity_id'''
    counts = defaultdict(Counter)
    current = None
    group = []

    def evaluate(rows):
        if len(rows) < 2:
            return
        country = rows[0][2]
        ranked = sorted(((token_sort_ratio(row[1],row[4]),
                          row[3], bool(row[5])) for row in rows),
                        key=lambda item: (-item[0], item[1]))
        if not any(positive for _,_,positive in ranked):
            return
        counts[country]['eligible_with_true_owner'] += 1
        counts[country]['best_correct'] += ranked[0][2]
        for minimum, margin in ((20,2),(30,3),(50,5),
                                (70,10),(80,10),(85,10),(90,10)):
            if ranked[0][0] >= minimum and ranked[0][0]-ranked[1][0] >= margin:
                key = f'gate_{minimum}_{margin}'
                counts[country][key] += 1
                counts[country][key + '_correct'] += ranked[0][2]

    cursor = con.execute(query)
    while chunk := cursor.fetchmany(100000):
        for row in chunk:
            if current is None:
                current = row[0]
            if row[0] != current:
                evaluate(group)
                group = []
                current = row[0]
            group.append(row)
    evaluate(group)
    con.close()
    return {'protocol':'Exact normalized-name S1 competitor groups of size 2-20 on supplied labeled train; truth used only to measure whether closest-address owner is correct',
            'counts':{country:dict(values) for country,values in counts.items()}}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    started=time.monotonic()
    result=run(args.db)
    result['seconds']=time.monotonic()-started
    path=Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
