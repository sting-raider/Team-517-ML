"""R005: exact blocker-v2 reproduction plus source-specific BM25 name retrieval.

This script is deliberately self-contained so it can run in a clean remote worker
without materializing the repository's full DuckDB database. It streams the complete
training TSVs, keeps only postings relevant to the fixed calibration anchors, and
verifies blocker-v2 against the committed retrieval-study baseline before reporting
the BM25 delta.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import time
from pathlib import Path

import duckdb
import numpy as np


DRIVE_FILES = {
    "train_source1.tsv": ("1nMO8x7VhzYgEF9dAd0uRr-RhMub0BqjM", 210_069_713),
    "train_source2.tsv": ("1aV5sSICdqErwCNeMKoAmuoVXWlKycqRC", 489_301_488),
    "train_source3.tsv": ("1qRSjQNC76FaLZs9_d1r60pLf2B2z_yxn", 503_705_637),
    "train_ground_truth.tsv": ("1xllXi0svJ-j9GWVfSBsMt1c-HivrV6uo", 127_015_583),
}
EXPECTED_ANCHORS = 4389
EXPECTED_PAIR_RECALL = 0.9458627913066248
EXPECTED_ORACLE = 0.9811781091658961


def fold(entity_id: str) -> str:
    bucket = int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100
    return "fit" if bucket < 60 else "early" if bucket < 75 else "calibrate" if bucket < 90 else "holdout"


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def download_files(data_dir: Path) -> None:
    import gdown

    data_dir.mkdir(parents=True, exist_ok=True)
    for name, (file_id, expected_size) in DRIVE_FILES.items():
        path = data_dir / name
        if not path.exists() or path.stat().st_size != expected_size:
            if path.exists():
                path.unlink()
            got = gdown.download(id=file_id, output=str(path), quiet=False)
            if not got:
                raise RuntimeError(f"gdown failed for {name}")
        size = path.stat().st_size
        if size != expected_size:
            raise RuntimeError(f"{name}: expected {expected_size} bytes, got {size}")
        print(f"verified {name}: {size:,} bytes", flush=True)


def connect(db: Path):
    con = duckdb.connect(str(db))
    con.execute("SET memory_limit='4GB'")
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


def target_docs(path: Path) -> str:
    p = sql_path(path)
    return f"""SELECT entity_id, coalesce(country,'') AS country,
        norm(business_name) AS n, norm(business_address) AS a
        FROM read_csv('{p}', delim='\\t', header=true, all_varchar=true)"""


def target_block_keys(path: Path) -> str:
    return f"""SELECT entity_id,country,k
        FROM ({target_docs(path)}) d, unnest(block_keys(n,a)) AS u(k)
        WHERE k IS NOT NULL"""


def target_name_docs(path: Path) -> str:
    p = sql_path(path)
    return f"""SELECT entity_id, coalesce(country,'') AS country,
        list_filter(string_split(norm(business_name),' '), x->len(x)>=3) AS toks
        FROM read_csv('{p}', delim='\\t', header=true, all_varchar=true)"""


def table_metrics(con, table: str) -> dict:
    rows = con.execute(f"""
        WITH cc AS (
            SELECT anchor,count(*)::BIGINT AS candidate_count FROM {table} GROUP BY anchor
        ), fc AS (
            SELECT e.anchor,count(*)::BIGINT AS found
            FROM eval_edges e JOIN {table} c USING(anchor,target)
            GROUP BY e.anchor
        )
        SELECT a.entity_id,a.country,a.truth_count,
               coalesce(cc.candidate_count,0),coalesce(fc.found,0)
        FROM anchor_truth a
        LEFT JOIN cc ON cc.anchor=a.entity_id
        LEFT JOIN fc ON fc.anchor=a.entity_id
        ORDER BY a.entity_id
    """).fetchall()
    truth = np.asarray([r[2] for r in rows], dtype=np.int64)
    cand = np.asarray([r[3] for r in rows], dtype=np.int64)
    found = np.asarray([r[4] for r in rows], dtype=np.int64)
    positive = truth > 0
    oracle = np.ones(len(rows), dtype=np.float64)
    oracle[positive] = 1.25 * found[positive] / (0.25 * truth[positive] + found[positive])
    total_truth = int(truth.sum())
    result = {
        "entities": len(rows),
        "singleton_count": int((truth == 0).sum()),
        "candidate_pairs": int(cand.sum()),
        "candidate_pair_recall": float(found.sum() / total_truth),
        "candidate_entity_recall": float(np.mean(found[positive] / truth[positive])),
        "all_matches_retrieved_rate": float(np.mean(found[positive] == truth[positive])),
        "blocking_oracle_macro_f0_5": float(np.mean(oracle)),
        "candidate_count_quantiles": dict(zip(
            ["p50", "p90", "p99", "max"],
            [float(x) for x in np.quantile(cand, [0.5, 0.9, 0.99, 1.0])],
        )),
    }
    countries = {}
    for country in sorted({r[1] for r in rows}):
        idx = np.asarray([r[1] == country for r in rows], dtype=bool)
        pos = idx & positive
        country_truth = int(truth[idx].sum())
        country_found = int(found[idx].sum())
        countries[country] = {
            "entities": int(idx.sum()),
            "candidate_pair_recall": float(country_found / country_truth) if country_truth else None,
            "candidate_entity_recall": float(np.mean(found[pos] / truth[pos])) if pos.any() else None,
            "all_matches_retrieved_rate": float(np.mean(found[pos] == truth[pos])) if pos.any() else None,
            "blocking_oracle_macro_f0_5": float(np.mean(oracle[idx])),
            "candidate_count_p50": float(np.quantile(cand[idx], 0.5)),
            "candidate_count_p90": float(np.quantile(cand[idx], 0.9)),
        }
    result["countries"] = countries
    source_rows = con.execute(f"""
        SELECT e.source,count(*) AS truth_pairs,
               count(*) FILTER (WHERE c.target IS NOT NULL) AS found_pairs
        FROM eval_edges_src e LEFT JOIN {table} c USING(anchor,target)
        GROUP BY e.source ORDER BY e.source
    """).fetchall()
    result["sources"] = {
        str(source): {
            "truth_pairs": int(total),
            "found_pairs": int(found_src),
            "pair_recall": float(found_src / total) if total else None,
        }
        for source,total,found_src in source_rows
    }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--bm25-per-source", type=int, default=64)
    ap.add_argument("--bm25-df-cap", type=int, default=5000)
    args = ap.parse_args()

    if args.download:
        download_files(args.data_dir)
    for name, (_, expected_size) in DRIVE_FILES.items():
        p = args.data_dir / name
        if not p.exists() or p.stat().st_size != expected_size:
            raise RuntimeError(f"missing or incomplete {p}")

    s1 = args.data_dir / "train_source1.tsv"
    s2 = args.data_dir / "train_source2.tsv"
    s3 = args.data_dir / "train_source3.tsv"
    gt = args.data_dir / "train_ground_truth.tsv"
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        args.db.unlink()
    con = connect(args.db)
    timings = {}
    t0 = time.time()

    phase = time.time()
    con.execute(f"""CREATE TABLE dev30k AS
        SELECT entity_id,coalesce(country,'') AS country,
               norm(business_name) AS n,norm(business_address) AS a
        FROM read_csv('{sql_path(s1)}', delim='\\t', header=true, all_varchar=true)
        ORDER BY md5('sample517:'||entity_id) LIMIT 30000""")
    ids = [r[0] for r in con.execute("SELECT entity_id FROM dev30k").fetchall()]
    calibrate = [i for i in ids if fold(i) == "calibrate"]
    con.execute("CREATE TABLE calibrate_ids(entity_id VARCHAR)")
    con.executemany("INSERT INTO calibrate_ids VALUES (?)", [(i,) for i in calibrate])
    con.execute("""CREATE TABLE anchors AS
        SELECT d.* FROM dev30k d JOIN calibrate_ids c USING(entity_id)""")
    anchor_count = con.execute("SELECT count(*) FROM anchors").fetchone()[0]
    if anchor_count != EXPECTED_ANCHORS:
        raise RuntimeError(f"calibration anchor count mismatch: {anchor_count} != {EXPECTED_ANCHORS}")
    con.execute(f"""CREATE TABLE truth AS
        SELECT source1_entity_id AS anchor,coalesce(matched_entity_ids,'') AS matches
        FROM read_csv('{sql_path(gt)}', delim='\\t', header=true, all_varchar=true)""")
    con.execute("""CREATE TABLE eval_truth AS
        SELECT a.entity_id AS anchor,t.matches FROM anchors a JOIN truth t ON t.anchor=a.entity_id""")
    con.execute("""CREATE TABLE eval_edges AS
        SELECT anchor,trim(unnest(string_split(matches,','))) AS target
        FROM eval_truth WHERE matches<>''""")
    con.execute("""CREATE TABLE anchor_truth AS
        SELECT a.entity_id,a.country,count(e.target)::BIGINT AS truth_count
        FROM anchors a LEFT JOIN eval_edges e ON e.anchor=a.entity_id
        GROUP BY a.entity_id,a.country""")
    timings["anchors_truth"] = time.time() - phase

    phase = time.time()
    con.execute("""CREATE TABLE all_query_keys AS
        SELECT entity_id AS anchor,country,k,left(k,2) AS kind
        FROM anchors,unnest(block_keys(n,a)) AS u(k)
        WHERE k IS NOT NULL""")
    con.execute("""CREATE TABLE wanted_keyhash AS
        SELECT DISTINCT hash(country,k) AS key FROM all_query_keys""")
    freq_sql = f"""
        CREATE TABLE key_freq AS
        SELECT key,count(*)::INTEGER AS freq FROM (
            SELECT hash(b.country,b.k) AS key FROM ({target_block_keys(s2)}) b
            JOIN wanted_keyhash w ON w.key=hash(b.country,b.k)
            UNION ALL
            SELECT hash(b.country,b.k) AS key FROM ({target_block_keys(s3)}) b
            JOIN wanted_keyhash w ON w.key=hash(b.country,b.k)
        ) x GROUP BY key
    """
    con.execute(freq_sql)
    con.execute("""CREATE TABLE query_keys AS
        SELECT anchor,hash(country,k) AS key,
               CASE left(k,2) WHEN 'n:' THEN 50.0 WHEN 'a:' THEN 40.0
                    WHEN 'w:' THEN 0.0 ELSE 8.0 END AS bonus,
               kind,f.freq,k
        FROM all_query_keys q JOIN key_freq f ON f.key=hash(q.country,q.k)
        WHERE f.freq<=1000
        QUALIFY kind IN ('n:','a:','h:','z:')
             OR row_number() OVER(PARTITION BY anchor,kind ORDER BY f.freq,k)<=4""")
    timings["baseline_freq"] = time.time() - phase

    phase = time.time()
    hit_parts = []
    for source,path in ((2,s2),(3,s3)):
        hit_parts.append(f"""
            SELECT q.anchor,b.entity_id AS target,{source}::INTEGER AS source,
                   sum(q.bonus+ln(10000001.0/q.freq))::FLOAT AS retrieval,
                   count(*)::SMALLINT AS hits
            FROM ({target_block_keys(path)}) b
            JOIN query_keys q ON q.key=hash(b.country,b.k)
            GROUP BY q.anchor,b.entity_id
        """)
    con.execute("CREATE TABLE baseline_hits AS " + " UNION ALL ".join(hit_parts))
    con.execute("""CREATE TABLE baseline_candidates AS
        SELECT anchor,target,source,retrieval,hits,
               row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC,target) AS base_rank
        FROM baseline_hits
        QUALIFY base_rank<=640""")
    timings["baseline_candidates"] = time.time() - phase

    phase = time.time()
    con.execute("""CREATE TABLE query_name_tokens AS
        SELECT DISTINCT entity_id AS anchor,country,token
        FROM anchors,unnest(list_filter(string_split(n,' '), x->len(x)>=3)) AS u(token)
        WHERE token<>''""")
    con.execute("""CREATE TABLE wanted_name_tokens AS
        SELECT DISTINCT country,token FROM query_name_tokens""")
    stat_parts = []
    token_parts = []
    for source,path in ((2,s2),(3,s3)):
        docs = target_name_docs(path)
        stat_parts.append(f"""
            SELECT {source}::INTEGER AS source,country,count(*)::BIGINT AS n_docs,
                   avg(len(toks))::DOUBLE AS avgdl
            FROM ({docs}) d GROUP BY country
        """)
        token_parts.append(f"""
            SELECT {source}::INTEGER AS source,x.entity_id,x.country,x.dl,x.token,count(*)::INTEGER AS tf
            FROM (
                SELECT d.entity_id,d.country,len(d.toks)::DOUBLE AS dl,unnest(d.toks) AS token
                FROM ({docs}) d
            ) x
            JOIN wanted_name_tokens w USING(country,token)
            GROUP BY x.entity_id,x.country,x.dl,x.token
        """)
    con.execute("CREATE TABLE bm25_stats AS " + " UNION ALL ".join(stat_parts))
    con.execute("CREATE TABLE bm25_target_tokens AS " + " UNION ALL ".join(token_parts))
    con.execute("""CREATE TABLE bm25_df AS
        SELECT source,country,token,count(*)::BIGINT AS df
        FROM bm25_target_tokens GROUP BY source,country,token""")
    timings["bm25_index"] = time.time() - phase

    phase = time.time()
    k1 = 1.2
    b = 0.75
    con.execute(f"""CREATE TABLE bm25_hits AS
        SELECT q.anchor,t.entity_id AS target,t.source,
               sum(
                 ln(1.0 + (s.n_docs-d.df+0.5)/(d.df+0.5))
                 * ((t.tf*({k1}+1.0)) /
                    (t.tf+{k1}*(1.0-{b}+{b}*t.dl/greatest(s.avgdl,1e-9))))
               )::FLOAT AS bm25,
               count(*)::SMALLINT AS matched_tokens
        FROM query_name_tokens q
        JOIN bm25_target_tokens t USING(country,token)
        JOIN bm25_df d USING(source,country,token)
        JOIN bm25_stats s USING(source,country)
        WHERE d.df<={int(args.bm25_df_cap)}
        GROUP BY q.anchor,t.entity_id,t.source""")
    con.execute(f"""CREATE TABLE bm25_candidates AS
        SELECT anchor,target,source,bm25,matched_tokens,
               row_number() OVER(PARTITION BY anchor,source ORDER BY bm25 DESC,target) AS source_rank
        FROM bm25_hits
        QUALIFY source_rank<={int(args.bm25_per_source)}""")
    con.execute("""CREATE TABLE bm25_global AS
        SELECT *,row_number() OVER(PARTITION BY anchor ORDER BY bm25 DESC,target) AS bm_rank
        FROM bm25_candidates""")
    con.execute("""CREATE TABLE union_candidates AS
        SELECT DISTINCT anchor,target FROM (
            SELECT anchor,target FROM baseline_candidates
            UNION ALL
            SELECT anchor,target FROM bm25_candidates
        )""")
    con.execute("""CREATE TABLE rrf_candidates AS
        WITH u AS (
            SELECT anchor,target,base_rank::DOUBLE AS base_rank,NULL::DOUBLE AS bm_rank
            FROM baseline_candidates
            UNION ALL
            SELECT anchor,target,NULL::DOUBLE AS base_rank,bm_rank::DOUBLE AS bm_rank
            FROM bm25_global
        ), a AS (
            SELECT anchor,target,min(base_rank) AS base_rank,min(bm_rank) AS bm_rank
            FROM u GROUP BY anchor,target
        ), scored AS (
            SELECT anchor,target,
                   coalesce(1.0/(60.0+base_rank),0.0)+coalesce(1.0/(60.0+bm_rank),0.0) AS rrf
            FROM a
        )
        SELECT anchor,target FROM scored
        QUALIFY row_number() OVER(PARTITION BY anchor ORDER BY rrf DESC,target)<=640""")
    timings["bm25_candidates_and_union"] = time.time() - phase

    phase = time.time()
    # Label truth targets by source for source-specific recall diagnostics only.
    con.execute(f"""CREATE TABLE eval_edges_src AS
        SELECT e.anchor,e.target,2::INTEGER AS source
        FROM eval_edges e
        JOIN read_csv('{sql_path(s2)}', delim='\\t', header=true, all_varchar=true) t
          ON t.entity_id=e.target
        UNION ALL
        SELECT e.anchor,e.target,3::INTEGER AS source
        FROM eval_edges e
        JOIN read_csv('{sql_path(s3)}', delim='\\t', header=true, all_varchar=true) t
          ON t.entity_id=e.target""")
    baseline = table_metrics(con, "baseline_candidates")
    if not math.isclose(baseline["candidate_pair_recall"], EXPECTED_PAIR_RECALL, rel_tol=0, abs_tol=1e-12):
        raise RuntimeError(
            f"baseline pair recall mismatch: {baseline['candidate_pair_recall']} != {EXPECTED_PAIR_RECALL}"
        )
    if not math.isclose(baseline["blocking_oracle_macro_f0_5"], EXPECTED_ORACLE, rel_tol=0, abs_tol=1e-12):
        raise RuntimeError(
            f"baseline oracle mismatch: {baseline['blocking_oracle_macro_f0_5']} != {EXPECTED_ORACLE}"
        )
    bm25_only = table_metrics(con, "bm25_candidates")
    union = table_metrics(con, "union_candidates")
    rrf = table_metrics(con, "rrf_candidates")

    marginal_rows = con.execute("""
        SELECT a.country,e.source,count(*)::BIGINT AS recovered_pairs,
               count(DISTINCT e.anchor)::BIGINT AS rescued_anchors
        FROM eval_edges_src e
        JOIN anchors a ON a.entity_id=e.anchor
        JOIN bm25_candidates m USING(anchor,target)
        LEFT JOIN baseline_candidates b USING(anchor,target)
        WHERE b.target IS NULL
        GROUP BY a.country,e.source ORDER BY a.country,e.source
    """).fetchall()
    added = con.execute("""
        SELECT count(*) FROM bm25_candidates m
        LEFT JOIN baseline_candidates b USING(anchor,target)
        WHERE b.target IS NULL
    """).fetchone()[0]
    timings["evaluation"] = time.time() - phase

    report = {
        "experiment_id": "R005",
        "task": "BM25/IDF-weighted normalized-name retrieval over blocker v2",
        "protocol": {
            "development_population": "first 30,000 train S1 anchors by md5('sample517:'||entity_id)",
            "evaluation_fold": "calibrate only via SHA256 fold517 protocol",
            "anchor_count": int(anchor_count),
            "target_inventory": "complete train source2 + source3",
            "baseline_candidate_cap": 640,
            "bm25": {
                "token_min_length": 3,
                "k1": k1,
                "b": b,
                "df_cap_per_country_source": int(args.bm25_df_cap),
                "top_per_source": int(args.bm25_per_source),
            },
            "fixed_baseline_reference": {
                "candidate_pair_recall": EXPECTED_PAIR_RECALL,
                "blocking_oracle_macro_f0_5": EXPECTED_ORACLE,
            },
            "no_confirmation_consumed": True,
        },
        "metrics": {
            "baseline_cap640": baseline,
            "bm25_only": bm25_only,
            "baseline_plus_bm25_union": union,
            "rrf_cap640": rrf,
        },
        "delta": {
            "union_pair_recall": union["candidate_pair_recall"] - baseline["candidate_pair_recall"],
            "union_oracle_macro_f0_5": union["blocking_oracle_macro_f0_5"] - baseline["blocking_oracle_macro_f0_5"],
            "rrf_pair_recall": rrf["candidate_pair_recall"] - baseline["candidate_pair_recall"],
            "rrf_oracle_macro_f0_5": rrf["blocking_oracle_macro_f0_5"] - baseline["blocking_oracle_macro_f0_5"],
            "bm25_new_candidates_not_in_baseline": int(added),
        },
        "marginal_positive_recovery": [
            {
                "country": country,
                "source": int(source),
                "recovered_pairs": int(pairs),
                "rescued_anchors": int(anchors),
            }
            for country,source,pairs,anchors in marginal_rows
        ],
        "timings_seconds": {k: float(v) for k,v in timings.items()},
        "elapsed_seconds": float(time.time() - t0),
        "peak_rss_mb": float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0),
        "data_file_sizes": {name: int((args.data_dir / name).stat().st_size) for name in DRIVE_FILES},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    con.close()


if __name__ == "__main__":
    main()
