"""R020a: full-data source-specific posting-frequency blocker experiment.

Compare current blocker-v2 pooled S2+S3 posting frequencies against a variant
that computes frequency, rare-key selection and IDF-like retrieval weights per
target source. Both outputs are globally capped at 640 candidates per anchor.

Only supplied challenge records are used. Ground truth is evaluation-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
EXPECTED_SINGLETONS = 252
EXPECTED_PAIR_RECALL = 0.9458627913066248
EXPECTED_ORACLE = 0.9811781091658961
CAP = 640


def fold(entity_id: str) -> str:
    bucket = int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100
    return "fit" if bucket < 60 else "early" if bucket < 75 else "calibrate" if bucket < 90 else "holdout"


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def read_tsv_expr(path: Path) -> str:
    # Use an actual tab byte in generated SQL. This deliberately avoids the
    # double-escaping trap caught by R005R.
    tab = "\t"
    return (
        f"read_csv('{sql_path(path)}', delim='{tab}', "
        "header=true, all_varchar=true)"
    )


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


def connect(path: Path):
    con = duckdb.connect(str(path))
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


def metrics(con, table: str) -> dict:
    rows = con.execute(f"""
        WITH cc AS (
            SELECT anchor,count(*)::BIGINT AS candidate_count
            FROM {table} GROUP BY anchor
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
        "mean_candidates": float(cand.mean()),
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
        ctruth = int(truth[idx].sum())
        cfound = int(found[idx].sum())
        countries[country] = {
            "entities": int(idx.sum()),
            "candidate_pairs": int(cand[idx].sum()),
            "mean_candidates": float(cand[idx].mean()),
            "candidate_pair_recall": float(cfound / ctruth) if ctruth else None,
            "candidate_entity_recall": float(np.mean(found[pos] / truth[pos])) if pos.any() else None,
            "all_matches_retrieved_rate": float(np.mean(found[pos] == truth[pos])) if pos.any() else None,
            "blocking_oracle_macro_f0_5": float(np.mean(oracle[idx])),
            "candidate_count_p50": float(np.quantile(cand[idx], 0.5)),
            "candidate_count_p90": float(np.quantile(cand[idx], 0.9)),
        }
    result["countries"] = countries

    source_rows = con.execute(f"""
        SELECT e.source,count(*)::BIGINT AS truth_pairs,
               count(*) FILTER (WHERE c.target IS NOT NULL)::BIGINT AS found_pairs
        FROM eval_edges_src e
        LEFT JOIN {table} c USING(anchor,target)
        GROUP BY e.source ORDER BY e.source
    """).fetchall()
    source_candidate_rows = {
        int(source): (int(pairs), int(anchors), float(pairs / len(rows)))
        for source,pairs,anchors in con.execute(f"""
            SELECT source,count(*)::BIGINT,count(DISTINCT anchor)::BIGINT
            FROM {table} GROUP BY source ORDER BY source
        """).fetchall()
    }
    result["sources"] = {}
    for source,total,found_src in source_rows:
        pairs, anchors_with_candidates, mean_per_anchor = source_candidate_rows.get(
            int(source), (0, 0, 0.0)
        )
        result["sources"][str(source)] = {
            "truth_pairs": int(total),
            "found_pairs": int(found_src),
            "pair_recall": float(found_src / total) if total else None,
            "candidate_pairs": pairs,
            "anchors_with_candidates": anchors_with_candidates,
            "mean_candidates_per_anchor": mean_per_anchor,
        }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--download", action="store_true")
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
    started = time.time()

    phase = time.time()
    con.execute(f"""CREATE TABLE dev30k AS
        SELECT entity_id,coalesce(country,'') AS country,
               norm(business_name) AS n,norm(business_address) AS a
        FROM {read_tsv_expr(s1)}
        ORDER BY md5('sample517:'||entity_id) LIMIT 30000""")
    ids = [r[0] for r in con.execute("SELECT entity_id FROM dev30k").fetchall()]
    calibration = [entity_id for entity_id in ids if fold(entity_id) == "calibrate"]
    con.execute("CREATE TABLE calibrate_ids(entity_id VARCHAR)")
    con.executemany("INSERT INTO calibrate_ids VALUES (?)", [(x,) for x in calibration])
    con.execute("""CREATE TABLE anchors AS
        SELECT d.* FROM dev30k d JOIN calibrate_ids c USING(entity_id)""")
    anchor_count = con.execute("SELECT count(*) FROM anchors").fetchone()[0]
    if anchor_count != EXPECTED_ANCHORS:
        raise RuntimeError(f"anchor mismatch: {anchor_count} != {EXPECTED_ANCHORS}")

    con.execute(f"""CREATE TABLE truth AS
        SELECT source1_entity_id AS anchor,coalesce(matched_entity_ids,'') AS matches
        FROM {read_tsv_expr(gt)}""")
    con.execute("""CREATE TABLE eval_truth AS
        SELECT a.entity_id AS anchor,t.matches
        FROM anchors a JOIN truth t ON t.anchor=a.entity_id""")
    con.execute("""CREATE TABLE eval_edges AS
        SELECT anchor,trim(unnest(string_split(matches,','))) AS target
        FROM eval_truth WHERE matches<>''""")
    con.execute("""CREATE TABLE anchor_truth AS
        SELECT a.entity_id,a.country,count(e.target)::BIGINT AS truth_count
        FROM anchors a LEFT JOIN eval_edges e ON e.anchor=a.entity_id
        GROUP BY a.entity_id,a.country""")
    singleton_count = con.execute(
        "SELECT count(*) FROM anchor_truth WHERE truth_count=0"
    ).fetchone()[0]
    if singleton_count != EXPECTED_SINGLETONS:
        raise RuntimeError(f"singleton mismatch: {singleton_count} != {EXPECTED_SINGLETONS}")

    con.execute("""CREATE TABLE all_query_keys AS
        SELECT entity_id AS anchor,country,k,hash(country,k) AS key,left(k,2) AS kind,
               CASE left(k,2) WHEN 'n:' THEN 50.0 WHEN 'a:' THEN 40.0
                    WHEN 'w:' THEN 0.0 ELSE 8.0 END AS bonus
        FROM anchors,unnest(block_keys(n,a)) AS u(k)
        WHERE k IS NOT NULL""")
    con.execute("CREATE TABLE wanted_keys AS SELECT DISTINCT key FROM all_query_keys")
    timings["anchors_truth_query_keys"] = time.time() - phase

    phase = time.time()
    parts = []
    for source,path in ((2,s2),(3,s3)):
        parts.append(f"""
            SELECT d.entity_id,{source}::INTEGER AS source,hash(d.country,k) AS key
            FROM (
                SELECT entity_id,coalesce(country,'') AS country,
                       norm(business_name) AS n,norm(business_address) AS a
                FROM {read_tsv_expr(path)}
            ) d,unnest(block_keys(d.n,d.a)) AS u(k)
            JOIN wanted_keys w ON w.key=hash(d.country,k)
            WHERE k IS NOT NULL
        """)
    con.execute("CREATE TABLE target_keys AS " + " UNION ALL ".join(parts))
    con.execute("CHECKPOINT")
    timings["target_key_scan"] = time.time() - phase

    phase = time.time()
    con.execute("""CREATE TABLE pooled_freq AS
        SELECT key,count(*)::INTEGER AS freq
        FROM target_keys GROUP BY key""")
    con.execute("""CREATE TABLE source_freq AS
        SELECT source,key,count(*)::INTEGER AS freq
        FROM target_keys GROUP BY source,key""")

    con.execute("""CREATE TABLE pooled_query_keys AS
        SELECT q.anchor,q.key,q.kind,q.bonus,f.freq,q.k
        FROM all_query_keys q JOIN pooled_freq f USING(key)
        WHERE f.freq<=1000
        QUALIFY kind IN ('n:','a:','h:','z:')
             OR row_number() OVER(
                 PARTITION BY anchor,kind ORDER BY f.freq,q.k
             )<=4""")

    con.execute("""CREATE TABLE source_query_keys AS
        SELECT q.anchor,f.source,q.key,q.kind,q.bonus,f.freq,q.k
        FROM all_query_keys q JOIN source_freq f USING(key)
        WHERE f.freq<=1000
        QUALIFY kind IN ('n:','a:','h:','z:')
             OR row_number() OVER(
                 PARTITION BY anchor,f.source,kind ORDER BY f.freq,q.k
             )<=4""")
    timings["frequency_and_query_selection"] = time.time() - phase

    phase = time.time()
    con.execute("""CREATE TABLE baseline_hits AS
        SELECT q.anchor,t.entity_id AS target,t.source,
               sum(q.bonus+ln(10000001.0/q.freq))::FLOAT AS retrieval,
               count(*)::SMALLINT AS hits
        FROM pooled_query_keys q JOIN target_keys t USING(key)
        GROUP BY q.anchor,t.entity_id,t.source""")
    con.execute(f"""CREATE TABLE baseline_candidates AS
        SELECT anchor,target,source,retrieval,hits
        FROM baseline_hits
        QUALIFY row_number() OVER(
            PARTITION BY anchor ORDER BY retrieval DESC,target
        )<={CAP}""")

    con.execute("""CREATE TABLE sourcefreq_hits AS
        SELECT q.anchor,t.entity_id AS target,t.source,
               sum(q.bonus+ln(10000001.0/q.freq))::FLOAT AS retrieval,
               count(*)::SMALLINT AS hits
        FROM source_query_keys q
        JOIN target_keys t ON t.source=q.source AND t.key=q.key
        GROUP BY q.anchor,t.entity_id,t.source""")
    con.execute(f"""CREATE TABLE sourcefreq_candidates AS
        SELECT anchor,target,source,retrieval,hits
        FROM sourcefreq_hits
        QUALIFY row_number() OVER(
            PARTITION BY anchor ORDER BY retrieval DESC,target
        )<={CAP}""")
    timings["candidate_generation"] = time.time() - phase

    phase = time.time()
    # Target-source map is evaluation metadata only; it never enters retrieval.
    con.execute(
        "CREATE TABLE target_source(entity_id VARCHAR PRIMARY KEY,source INTEGER)"
    )
    for source,path in ((2,s2),(3,s3)):
        con.execute(
            f"INSERT INTO target_source SELECT entity_id,{source} FROM {read_tsv_expr(path)}"
        )
    con.execute("""CREATE TABLE eval_edges_src AS
        SELECT e.anchor,e.target,t.source
        FROM eval_edges e JOIN target_source t ON t.entity_id=e.target""")

    baseline = metrics(con, "baseline_candidates")
    if not math.isclose(
        baseline["candidate_pair_recall"], EXPECTED_PAIR_RECALL,
        rel_tol=0, abs_tol=1e-12
    ):
        raise RuntimeError(
            "baseline pair recall mismatch: "
            f"{baseline['candidate_pair_recall']} != {EXPECTED_PAIR_RECALL}"
        )
    if not math.isclose(
        baseline["blocking_oracle_macro_f0_5"], EXPECTED_ORACLE,
        rel_tol=0, abs_tol=1e-12
    ):
        raise RuntimeError(
            "baseline oracle mismatch: "
            f"{baseline['blocking_oracle_macro_f0_5']} != {EXPECTED_ORACLE}"
        )

    variant = metrics(con, "sourcefreq_candidates")

    marginal = con.execute("""
        WITH b AS (
            SELECT e.anchor,e.target,e.source,a.country
            FROM eval_edges_src e
            JOIN anchors a ON a.entity_id=e.anchor
            JOIN baseline_candidates c USING(anchor,target)
        ), v AS (
            SELECT e.anchor,e.target,e.source,a.country
            FROM eval_edges_src e
            JOIN anchors a ON a.entity_id=e.anchor
            JOIN sourcefreq_candidates c USING(anchor,target)
        ), recovered AS (
            SELECT 'recovered' AS direction,v.*
            FROM v LEFT JOIN b USING(anchor,target)
            WHERE b.target IS NULL
        ), lost AS (
            SELECT 'lost' AS direction,b.*
            FROM b LEFT JOIN v USING(anchor,target)
            WHERE v.target IS NULL
        )
        SELECT direction,country,source,count(*)::BIGINT AS pairs,
               count(DISTINCT anchor)::BIGINT AS anchors
        FROM (SELECT * FROM recovered UNION ALL SELECT * FROM lost)
        GROUP BY direction,country,source
        ORDER BY direction,country,source
    """).fetchall()

    membership = con.execute("""
        WITH b AS (SELECT anchor,target FROM baseline_candidates),
             v AS (SELECT anchor,target FROM sourcefreq_candidates)
        SELECT
            (SELECT count(*) FROM v LEFT JOIN b USING(anchor,target)
             WHERE b.target IS NULL) AS variant_only,
            (SELECT count(*) FROM b LEFT JOIN v USING(anchor,target)
             WHERE v.target IS NULL) AS baseline_only
    """).fetchone()

    selected_key_delta = con.execute("""
        WITH p AS (
            SELECT anchor,key FROM pooled_query_keys
        ), s AS (
            SELECT anchor,source,key FROM source_query_keys
        )
        SELECT source,
               count(*) FILTER (WHERE p.key IS NULL)::BIGINT AS source_selected_not_pooled,
               count(*)::BIGINT AS source_selected_total
        FROM s LEFT JOIN p USING(anchor,key)
        GROUP BY source ORDER BY source
    """).fetchall()

    suppressed = con.execute("""
        SELECT f.source,
               count(*)::BIGINT AS source_key_rows_with_source_freq_le_1000,
               count(*) FILTER (
                   WHERE p.freq>1000
               )::BIGINT AS rows_suppressed_by_pooled_cutoff
        FROM source_freq f
        JOIN pooled_freq p USING(key)
        WHERE f.freq<=1000
        GROUP BY f.source ORDER BY f.source
    """).fetchall()

    timings["evaluation"] = time.time() - phase

    report = {
        "experiment_id": "R020a",
        "task": "Source-specific posting frequency versus pooled S2+S3 frequency",
        "protocol": {
            "development_population": "first 30,000 S1 anchors by md5('sample517:'||entity_id)",
            "evaluation_fold": "calibrate only via fold517 SHA256 protocol",
            "anchor_count": int(anchor_count),
            "candidate_cap": CAP,
            "target_inventory": "complete train source2 + source3",
            "variant": (
                "frequency cutoff, rare-key selection and retrieval frequency "
                "computed separately for source2/source3; same global cap 640"
            ),
            "baseline_reference": {
                "candidate_pair_recall": EXPECTED_PAIR_RECALL,
                "blocking_oracle_macro_f0_5": EXPECTED_ORACLE,
            },
            "no_confirmation_consumed": True,
            "sampling": "none",
        },
        "metrics": {
            "pooled_frequency_baseline": baseline,
            "source_specific_frequency": variant,
        },
        "delta": {
            "candidate_pair_recall": (
                variant["candidate_pair_recall"] - baseline["candidate_pair_recall"]
            ),
            "candidate_entity_recall": (
                variant["candidate_entity_recall"] - baseline["candidate_entity_recall"]
            ),
            "all_matches_retrieved_rate": (
                variant["all_matches_retrieved_rate"] - baseline["all_matches_retrieved_rate"]
            ),
            "blocking_oracle_macro_f0_5": (
                variant["blocking_oracle_macro_f0_5"]
                - baseline["blocking_oracle_macro_f0_5"]
            ),
            "mean_candidates": variant["mean_candidates"] - baseline["mean_candidates"],
        },
        "marginal_positive_membership": [
            {
                "direction": direction,
                "country": country,
                "source": int(source),
                "pairs": int(pairs),
                "anchors": int(anchors),
            }
            for direction,country,source,pairs,anchors in marginal
        ],
        "candidate_membership_change": {
            "variant_only": int(membership[0]),
            "baseline_only": int(membership[1]),
        },
        "source_selected_key_delta": [
            {
                "source": int(source),
                "source_selected_not_pooled": int(new),
                "source_selected_total": int(total),
            }
            for source,new,total in selected_key_delta
        ],
        "pooled_cutoff_suppression": [
            {
                "source": int(source),
                "source_key_rows_with_source_freq_le_1000": int(total),
                "rows_suppressed_by_pooled_cutoff": int(dropped),
            }
            for source,total,dropped in suppressed
        ],
        "timings_seconds": {k: float(v) for k,v in timings.items()},
        "elapsed_seconds": float(time.time() - started),
        "peak_rss_mb": float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0),
        "data_file_sizes": {
            name: int((args.data_dir / name).stat().st_size)
            for name in DRIVE_FILES
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    con.close()


if __name__ == "__main__":
    main()
