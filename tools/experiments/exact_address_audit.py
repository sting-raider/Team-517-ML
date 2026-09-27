"""Census of exact normalized-address links using supplied training labels."""

import argparse
import json
import time

import duckdb


QUERY = """
WITH unique_a AS (
  SELECT country, a, min(entity_id) AS anchor
  FROM train WHERE source=1 AND a<>''
  GROUP BY country,a HAVING count(*)=1
), pairs AS (
  SELECT s.anchor,t.entity_id AS target,s.a,t.n AS target_name,x.n AS anchor_name,
         t.source AS target_source,s.country
  FROM unique_a s
  JOIN train t ON t.country=s.country AND t.a=s.a AND t.source IN (2,3)
  JOIN train x ON x.entity_id=s.anchor
)
SELECT country,target_source,
       CASE WHEN target_name=anchor_name THEN 'name_exact' ELSE 'name_diff' END AS bucket,
       count(*) AS total,count(e.target) AS true_matches
FROM pairs p LEFT JOIN edges e ON e.anchor=p.anchor AND e.target=p.target
GROUP BY 1,2,3 ORDER BY 1,2,3
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='artifacts/data.duckdb')
    parser.add_argument('--out', default='reports/exact_address_audit.json')
    args = parser.parse_args()
    started = time.time()
    con = duckdb.connect(args.db, read_only=True)
    con.execute('SET threads=8')
    rows = con.execute(QUERY).fetchall()
    report = {'rows': [dict(zip(('country','source','bucket','pairs','true'), row))
                       for row in rows], 'seconds': time.time()-started}
    with open(args.out, 'w', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
