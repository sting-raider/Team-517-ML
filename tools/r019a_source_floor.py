"""Full-data R019a: source-floor retrieval at fixed global cap.

Uses only supplied challenge TSVs. It reconstructs the exact blocker-v2 query-key
semantics for the established calibration anchors while materializing postings only
for hashes queried by those anchors, then compares the legacy joint top-k against
small per-source floors at the same total cap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import duckdb

EXPECTED_BASELINE = {
    "entities": 4389,
    "candidate_pair_recall": 0.9458627913066248,
    "candidate_entity_recall": 0.9454912308973222,
    "all_matches_retrieved_rate": 0.8411892675852066,
    "blocking_oracle_macro_f0_5": 0.9811781091658961,
    "candidate_count_quantiles": {"p50": 597.0, "p90": 640.0, "p99": 640.0, "max": 640.0},
}


def fold(entity_id: str) -> str:
    bucket = int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100
    return "fit" if bucket < 60 else "early" if bucket < 75 else "calibrate" if bucket < 90 else "holdout"


def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("SET memory_limit='5GB'")
    con.execute("SET threads=4")
    con.execute("SET preserve_insertion_order=false")
    con.execute(r"""CREATE OR REPLACE MACRO norm(s) AS
        trim(regexp_replace(lower(strip_accents(coalesce(s, ''))), '[^\p{L}\p{N}]+', ' ', 'g'))""")
    con.execute(r"""CREATE OR REPLACE MACRO address_words(a) AS
        list_filter(string_split(a,' '), x->len(x)>=3 AND NOT regexp_full_match(x,'[0-9]+')
        AND x NOT IN ('road','street','avenue','drive','lane','floor','near','opposite','the','and','unit','plot','no'))""")
    con.execute(r"""CREATE OR REPLACE MACRO block_keys(n,a) AS list_distinct(list_concat(
        [CASE WHEN n<>'' THEN 'n:'||replace(n,' ','') END,
         CASE WHEN a<>'' THEN 'a:'||replace(a,' ','') END,
         CASE WHEN len(n)>=4 AND regexp_extract(a,'[0-9]+')<>''
              THEN 'h:'||left(replace(n,' ',''),6)||':'||regexp_extract(a,'[0-9]+') END,
         CASE WHEN len(n)>=4 AND regexp_extract(a,'[0-9]+[^0-9]*$',0)<>''
              THEN 'z:'||left(replace(n,' ',''),6)||':'||regexp_extract(a,'([0-9]+)[^0-9]*$',1) END],
        list_transform(list_filter(string_split(n,' '), x->len(x)>=3), x->'w:'||x),
        list_transform(address_words(a), x->'u:'||x),
        list_transform(range(1,len(address_words(a))), i->'v:'||
            least(address_words(a)[i],address_words(a)[i+1])||':'||greatest(address_words(a)[i],address_words(a)[i+1])),
        CASE WHEN regexp_extract(a,'[0-9]+')<>'' THEN
            list_transform(address_words(a), x->'d:'||regexp_extract(a,'[0-9]+')||':'||x) ELSE [] END))""")
    return con


def metrics(con, table: str) -> dict:
    con.execute(f"""CREATE OR REPLACE TEMP TABLE cand_counts AS
        SELECT anchor, count(*)::INTEGER AS candidate_count,
               count(*) FILTER (WHERE source=2)::INTEGER AS cand_s2,
               count(*) FILTER (WHERE source=3)::INTEGER AS cand_s3
        FROM {table} GROUP BY anchor""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE found_counts AS
        SELECT c.anchor, count(*)::INTEGER AS found,
               count(*) FILTER (WHERE e.source=2)::INTEGER AS found_s2,
               count(*) FILTER (WHERE e.source=3)::INTEGER AS found_s3
        FROM {table} c JOIN truth_edges e ON c.anchor=e.anchor AND c.target=e.target
        GROUP BY c.anchor""")
    con.execute("""CREATE OR REPLACE TEMP TABLE per_anchor AS
        SELECT a.anchor,a.country,a.truth_count,a.truth_s2,a.truth_s3,
               coalesce(c.candidate_count,0)::INTEGER AS candidate_count,
               coalesce(c.cand_s2,0)::INTEGER AS cand_s2,
               coalesce(c.cand_s3,0)::INTEGER AS cand_s3,
               coalesce(f.found,0)::INTEGER AS found,
               coalesce(f.found_s2,0)::INTEGER AS found_s2,
               coalesce(f.found_s3,0)::INTEGER AS found_s3
        FROM eval_anchors a
        LEFT JOIN cand_counts c USING(anchor)
        LEFT JOIN found_counts f USING(anchor)""")

    def row(where: str = "TRUE"):
        q = f"""SELECT
            count(*)::BIGINT AS entities,
            sum(found)::DOUBLE / nullif(sum(truth_count),0) AS pair_recall,
            avg(found::DOUBLE/truth_count) FILTER (WHERE truth_count>0) AS entity_recall,
            avg((found=truth_count)::INTEGER) FILTER (WHERE truth_count>0) AS all_matches,
            avg(CASE WHEN truth_count=0 THEN 1.0
                     ELSE 1.25*found/(0.25*truth_count+found) END) AS oracle,
            avg(candidate_count)::DOUBLE AS mean_candidates,
            quantile_cont(candidate_count,0.5) AS p50,
            quantile_cont(candidate_count,0.9) AS p90,
            quantile_cont(candidate_count,0.99) AS p99,
            max(candidate_count)::DOUBLE AS max_candidates,
            sum(found_s2)::DOUBLE/nullif(sum(truth_s2),0) AS s2_pair_recall,
            sum(found_s3)::DOUBLE/nullif(sum(truth_s3),0) AS s3_pair_recall
            FROM per_anchor WHERE {where}"""
        x = con.execute(q).fetchone()
        return {
            "entities": int(x[0]),
            "candidate_pair_recall": float(x[1]),
            "candidate_entity_recall": float(x[2]),
            "all_matches_retrieved_rate": float(x[3]),
            "blocking_oracle_macro_f0_5": float(x[4]),
            "mean_candidates": float(x[5]),
            "candidate_count_quantiles": {"p50": float(x[6]), "p90": float(x[7]), "p99": float(x[8]), "max": float(x[9])},
            "s2_pair_recall": float(x[10]),
            "s3_pair_recall": float(x[11]),
        }

    out = row()
    out["by_country"] = {country: row("country="+repr(country)) for country in ("US","India")}
    hit_starved = con.execute(f"""WITH avail AS (
            SELECT anchor,count(DISTINCT source) AS n FROM hits GROUP BY anchor
        ), chosen AS (
            SELECT anchor,count(DISTINCT source) AS n FROM {table} GROUP BY anchor
        )
        SELECT count(*) FILTER (WHERE avail.n=2 AND coalesce(chosen.n,0)<2),
               count(*) FILTER (WHERE coalesce(chosen.n,0)=1),
               count(*) FILTER (WHERE coalesce(chosen.n,0)=0)
        FROM eval_anchors a LEFT JOIN avail USING(anchor) LEFT JOIN chosen USING(anchor)""").fetchone()
    out["source_starvation"] = {
        "both_sources_available_but_one_absent_after_cap": int(hit_starved[0]),
        "one_source_only_after_cap": int(hit_starved[1]),
        "zero_candidates": int(hit_starved[2]),
    }
    return out


def create_candidates(con, table: str, cap: int, source_floor: int | None):
    if source_floor is None:
        con.execute(f"""CREATE OR REPLACE TABLE {table} AS
            SELECT anchor,target,source,retrieval FROM hits
            QUALIFY row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC,target)<={cap}""")
    else:
        con.execute(f"""CREATE OR REPLACE TABLE {table} AS
            WITH ranked AS (
                SELECT *,row_number() OVER(
                    PARTITION BY anchor,source ORDER BY retrieval DESC,target
                ) AS source_rank FROM hits
            )
            SELECT anchor,target,source,retrieval FROM ranked
            QUALIFY row_number() OVER(
                PARTITION BY anchor
                ORDER BY CASE WHEN source_rank<={source_floor} THEN 0 ELSE 1 END,
                         retrieval DESC,target
            )<={cap}""")


def found_edge_delta(con, variant: str, baseline: str = "cand_joint") -> dict:
    recovered = con.execute(f"""SELECT count(*) FROM (
        SELECT v.anchor,v.target FROM {variant} v
        JOIN truth_edges e ON v.anchor=e.anchor AND v.target=e.target
        EXCEPT
        SELECT b.anchor,b.target FROM {baseline} b
        JOIN truth_edges e ON b.anchor=e.anchor AND b.target=e.target
    )""").fetchone()[0]
    lost = con.execute(f"""SELECT count(*) FROM (
        SELECT b.anchor,b.target FROM {baseline} b
        JOIN truth_edges e ON b.anchor=e.anchor AND b.target=e.target
        EXCEPT
        SELECT v.anchor,v.target FROM {variant} v
        JOIN truth_edges e ON v.anchor=e.anchor AND v.target=e.target
    )""").fetchone()[0]
    changed = con.execute(f"""SELECT count(*) FROM (
        (SELECT anchor,target FROM {variant} EXCEPT SELECT anchor,target FROM {baseline})
        UNION ALL
        (SELECT anchor,target FROM {baseline} EXCEPT SELECT anchor,target FROM {variant})
    )""").fetchone()[0]
    return {"recovered_positive_edges": int(recovered), "lost_positive_edges": int(lost), "candidate_symmetric_difference_edges": int(changed)}


def parity_check(actual: dict) -> dict:
    checks = {}
    for key in ("entities","candidate_pair_recall","candidate_entity_recall","all_matches_retrieved_rate","blocking_oracle_macro_f0_5"):
        expected = EXPECTED_BASELINE[key]
        got = actual[key]
        checks[key] = {"expected": expected, "actual": got, "pass": (got == expected if key=="entities" else abs(got-expected) <= 1e-12)}
    for q,expected in EXPECTED_BASELINE["candidate_count_quantiles"].items():
        got = actual["candidate_count_quantiles"][q]
        checks["candidate_"+q] = {"expected": expected, "actual": got, "pass": abs(got-expected) <= 1e-12}
    return {"pass": all(x["pass"] for x in checks.values()), "checks": checks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cap", type=int, default=640)
    ap.add_argument("--floors", default="1,2,4,8")
    args = ap.parse_args()
    floors = [int(x) for x in args.floors.split(",") if x]
    started = time.time()
    stages = {}
    con = connect(args.db)
    s1 = str((args.data/"train_source1.tsv").resolve())
    s2 = str((args.data/"train_source2.tsv").resolve())
    s3 = str((args.data/"train_source3.tsv").resolve())
    gt = str((args.data/"train_ground_truth.tsv").resolve())

    t=time.time()
    con.execute("""CREATE OR REPLACE TABLE anchor_sample AS
        SELECT entity_id,country,norm(business_name) AS n,norm(business_address) AS a
        FROM read_csv(?,delim='\\t',header=true,all_varchar=true)
        ORDER BY md5('sample517:'||entity_id) LIMIT 30000""",[s1])
    ids=[r[0] for r in con.execute("SELECT entity_id FROM anchor_sample").fetchall()]
    cal=[x for x in ids if fold(x)=="calibrate"]
    con.execute("CREATE OR REPLACE TABLE cal_ids(entity_id VARCHAR)")
    con.executemany("INSERT INTO cal_ids VALUES (?)",[(x,) for x in cal])
    con.execute("""CREATE OR REPLACE TABLE anchors AS
        SELECT s.* FROM anchor_sample s JOIN cal_ids USING(entity_id)""")
    if len(cal)!=4389:
        raise RuntimeError(f"Calibration anchor mismatch: {len(cal)} != 4389")
    stages["anchors_seconds"]=time.time()-t

    t=time.time()
    con.execute("""CREATE OR REPLACE TABLE anchor_rawkeys AS
        SELECT entity_id AS anchor,hash(country,k) AS key,
               CASE left(k,2) WHEN 'n:' THEN 50.0 WHEN 'a:' THEN 40.0
                    WHEN 'w:' THEN 0.0 ELSE 8.0 END AS bonus,
               left(k,2) AS kind,k
        FROM anchors CROSS JOIN unnest(block_keys(n,a)) AS u(k)
        WHERE k IS NOT NULL""")
    con.execute("CREATE OR REPLACE TABLE anchor_key_hashes AS SELECT DISTINCT key FROM anchor_rawkeys")
    stages["anchor_keys_seconds"]=time.time()-t

    t=time.time()
    con.execute("""CREATE OR REPLACE TABLE target_postings AS
        WITH targets AS (
            SELECT entity_id,2 AS source,country,norm(business_name) AS n,norm(business_address) AS a
            FROM read_csv(?,delim='\\t',header=true,all_varchar=true)
            UNION ALL
            SELECT entity_id,3 AS source,country,norm(business_name) AS n,norm(business_address) AS a
            FROM read_csv(?,delim='\\t',header=true,all_varchar=true)
        )
        SELECT t.entity_id AS target,t.source,hash(t.country,u.k) AS key
        FROM targets t CROSS JOIN unnest(block_keys(t.n,t.a)) AS u(k)
        JOIN anchor_key_hashes q ON q.key=hash(t.country,u.k)
        WHERE u.k IS NOT NULL""",[s2,s3])
    con.execute("CREATE OR REPLACE TABLE freq AS SELECT key,count(*)::INTEGER AS freq FROM target_postings GROUP BY key")
    stages["target_scan_seconds"]=time.time()-t

    t=time.time()
    con.execute("""CREATE OR REPLACE TABLE query_keys AS
        SELECT q.anchor,q.key,q.bonus,q.kind,f.freq,q.k
        FROM anchor_rawkeys q JOIN freq f USING(key)
        WHERE f.freq<=1000
        QUALIFY kind IN ('n:','a:','h:','z:')
            OR row_number() OVER(PARTITION BY anchor,kind ORDER BY f.freq,k)<=4""")
    con.execute("""CREATE OR REPLACE TABLE hits AS
        SELECT q.anchor,p.target,p.source,
               sum(q.bonus+ln(10000001.0/q.freq))::FLOAT AS retrieval,
               count(*)::SMALLINT AS hits
        FROM query_keys q JOIN target_postings p USING(key)
        GROUP BY q.anchor,p.target,p.source""")
    stages["hits_seconds"]=time.time()-t

    t=time.time()
    con.execute("""CREATE OR REPLACE TABLE truth_raw AS
        SELECT g.source1_entity_id AS anchor,coalesce(g.matched_entity_ids,'') AS matches
        FROM read_csv(?,delim='\\t',header=true,all_varchar=true) g
        JOIN anchors a ON g.source1_entity_id=a.entity_id""",[gt])
    con.execute("""CREATE OR REPLACE TABLE truth_edges AS
        SELECT anchor,trim(u.target) AS target,
               CASE WHEN trim(u.target) LIKE 'S2-%' THEN 2 ELSE 3 END AS source
        FROM truth_raw CROSS JOIN unnest(string_split(matches,',')) AS u(target)
        WHERE matches<>''""")
    con.execute("""CREATE OR REPLACE TABLE eval_anchors AS
        SELECT a.entity_id AS anchor,a.country,
               count(e.target)::INTEGER AS truth_count,
               count(e.target) FILTER(WHERE e.source=2)::INTEGER AS truth_s2,
               count(e.target) FILTER(WHERE e.source=3)::INTEGER AS truth_s3
        FROM anchors a LEFT JOIN truth_edges e ON a.entity_id=e.anchor
        GROUP BY a.entity_id,a.country""")
    stages["truth_seconds"]=time.time()-t

    result={
        "experiment":"R019a",
        "protocol":{
            "sample":"30,000 smallest md5(sample517:<entity_id>); calibration fold only",
            "fold":"sha256(fold517:<entity_id>) first8 mod100; calibrate buckets 75-89",
            "candidate_cap":args.cap,
            "floors":floors,
            "frequency_scope":"pooled S2+S3, identical to blocker v2",
            "query_key_semantics":"blocker v2 exact; postings materialized only for hashes queried by calibration anchors",
        },
        "inventory":{
            "anchors":len(cal),
            "target_postings":int(con.execute("SELECT count(*) FROM target_postings").fetchone()[0]),
            "query_keys":int(con.execute("SELECT count(*) FROM query_keys").fetchone()[0]),
            "hits":int(con.execute("SELECT count(*) FROM hits").fetchone()[0]),
            "truth_edges":int(con.execute("SELECT count(*) FROM truth_edges").fetchone()[0]),
        },
        "stages_seconds":stages,
        "baseline":{},
        "variants":{},
    }
    create_candidates(con,"cand_joint",args.cap,None)
    result["baseline"]=metrics(con,"cand_joint")
    result["baseline_parity"]=parity_check(result["baseline"])

    for floor in floors:
        name=f"cand_floor_{floor}"
        t=time.time()
        create_candidates(con,name,args.cap,floor)
        m=metrics(con,name)
        m["delta_vs_baseline"]={
            "candidate_pair_recall":m["candidate_pair_recall"]-result["baseline"]["candidate_pair_recall"],
            "candidate_entity_recall":m["candidate_entity_recall"]-result["baseline"]["candidate_entity_recall"],
            "all_matches_retrieved_rate":m["all_matches_retrieved_rate"]-result["baseline"]["all_matches_retrieved_rate"],
            "blocking_oracle_macro_f0_5":m["blocking_oracle_macro_f0_5"]-result["baseline"]["blocking_oracle_macro_f0_5"],
        }
        m["edge_delta"]=found_edge_delta(con,name)
        m["selection_seconds"]=time.time()-t
        result["variants"][str(floor)]=m

    result["runtime_seconds"]=time.time()-started
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,indent=2,sort_keys=True))
    con.close()
    if not result["baseline_parity"]["pass"]:
        print("BASELINE PARITY FAILED; refusing to interpret variants",file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    raise SystemExit(main())
