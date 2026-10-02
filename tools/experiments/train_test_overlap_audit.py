"""Measure lawful supplied-data text overlap between labeled and test inventories."""

import json
import time

import duckdb


def main():
    start=time.time()
    con=duckdb.connect('artifacts/data.duckdb',read_only=True)
    con.execute('SET threads=8')
    q='''SELECT t.country, count(*) test_s1,
      count_if(n.hit IS NOT NULL) name_overlap,
      count_if(na.hit IS NOT NULL) name_address_overlap,
      count_if(a.hit IS NOT NULL) address_overlap
      FROM test t
      LEFT JOIN (SELECT DISTINCT country,n,1 hit FROM train WHERE source=1 AND n<>'') n
        ON t.country=n.country AND t.n=n.n
      LEFT JOIN (SELECT DISTINCT country,n,a,1 hit FROM train WHERE source=1 AND n<>'' AND a<>'') na
        ON t.country=na.country AND t.n=na.n AND t.a=na.a
      LEFT JOIN (SELECT DISTINCT country,a,1 hit FROM train WHERE source=1 AND a<>'') a
        ON t.country=a.country AND t.a=a.a
      WHERE t.source=1 GROUP BY 1 ORDER BY 1'''
    rows=con.execute(q).fetchall()
    result={'rows':[dict(zip(('country','test_s1','name_overlap','name_address_overlap','address_overlap'),r)) for r in rows],
            'seconds':time.time()-start}
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
