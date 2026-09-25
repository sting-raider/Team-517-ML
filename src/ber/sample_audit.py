"""Audit representativeness of deterministic Team 517 anchor windows.

Reads only complete train Source-1 and ground-truth TSVs. It reproduces the
repository's md5 sample ordering and SHA-256 fold assignment. The only
confirmation rows characterized are the two already-consumed 5k windows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from .data import connect


def fold(entity_id: str) -> str:
    bucket = int(hashlib.sha256(("fold517:" + entity_id).encode()).hexdigest()[:8], 16) % 100
    return "fit" if bucket < 60 else "early" if bucket < 75 else "calibrate" if bucket < 90 else "holdout"


def proportion_z(p: float, population_p: float, n: int) -> float:
    """Descriptive z-score under pseudo-random hash sampling, not a model claim."""
    if not n or not 0 < population_p < 1:
        return 0.0
    se = math.sqrt(population_p * (1.0 - population_p) / n)
    return (p - population_p) / se


def _summarize(con, relation: str) -> dict:
    row = con.execute(f"""SELECT
        count(*)::BIGINT,
        count(*) FILTER (WHERE country='US')::BIGINT,
        count(*) FILTER (WHERE country='India')::BIGINT,
        count(*) FILTER (WHERE truth_count=0)::BIGINT,
        avg(truth_count)::DOUBLE,
        stddev_pop(truth_count)::DOUBLE,
        avg((business_name='')::INTEGER)::DOUBLE,
        avg((business_address='')::INTEGER)::DOUBLE,
        avg(length(business_name))::DOUBLE,
        stddev_pop(length(business_name))::DOUBLE,
        avg(length(business_address))::DOUBLE,
        stddev_pop(length(business_address))::DOUBLE,
        avg(len(regexp_extract_all(business_name,'\\S+')))::DOUBLE,
        stddev_pop(len(regexp_extract_all(business_name,'\\S+')))::DOUBLE,
        avg(len(regexp_extract_all(business_address,'\\S+')))::DOUBLE,
        stddev_pop(len(regexp_extract_all(business_address,'\\S+')))::DOUBLE
        FROM {relation}""").fetchone()
    n, us, india, singletons = map(int, row[:4])
    card_counts = dict(con.execute(f"""SELECT
        CASE WHEN truth_count>=5 THEN '5+' ELSE cast(truth_count AS VARCHAR) END,
        count(*)::BIGINT FROM {relation} GROUP BY 1""").fetchall())
    country_rows = con.execute(f"""SELECT country,count(*)::BIGINT,
        avg((truth_count=0)::INTEGER)::DOUBLE,avg(truth_count)::DOUBLE
        FROM {relation} GROUP BY country ORDER BY country""").fetchall()
    return {
        "n": n,
        "country_counts": {"India": india, "US": us},
        "country_share": {"India": india/n, "US": us/n},
        "singleton_count": singletons,
        "singleton_rate": singletons/n,
        "mean_truth_cardinality": float(row[4]),
        "truth_cardinality_sd": float(row[5]),
        "truth_cardinality_distribution": {
            k: int(card_counts.get(k, 0))/n for k in ("0","1","2","3","4","5+")
        },
        "name_missing_rate": float(row[6]),
        "address_missing_rate": float(row[7]),
        "name_len": {"mean": float(row[8]), "sd": float(row[9])},
        "address_len": {"mean": float(row[10]), "sd": float(row[11])},
        "name_tokens": {"mean": float(row[12]), "sd": float(row[13])},
        "address_tokens": {"mean": float(row[14]), "sd": float(row[15])},
        "by_country": {
            c: {"n": int(cn), "singleton_rate": float(sr), "mean_truth_cardinality": float(mc)}
            for c, cn, sr, mc in country_rows
        },
    }


def _effects(sample: dict, population: dict) -> dict:
    out = {}
    for metric in ("singleton_rate", "name_missing_rate", "address_missing_rate"):
        p, p0 = sample[metric], population[metric]
        out[metric] = {"delta_pp": 100*(p-p0), "z_hash_random": proportion_z(p, p0, sample["n"])}
    for country in ("US", "India"):
        p, p0 = sample["country_share"][country], population["country_share"][country]
        out[f"country_share.{country}"] = {
            "delta_pp": 100*(p-p0), "z_hash_random": proportion_z(p, p0, sample["n"])
        }
        p = sample["by_country"][country]["singleton_rate"]
        p0 = population["by_country"][country]["singleton_rate"]
        country_n = sample["by_country"][country]["n"]
        out[f"singleton_rate.{country}"] = {
            "delta_pp": 100*(p-p0), "z_hash_random": proportion_z(p, p0, country_n)
        }
        p = sample["by_country"][country]["singleton_rate"]
        p0 = population["by_country"][country]["singleton_rate"]
        cn = sample["by_country"][country]["n"]
        out[f"singleton_rate.{country}"] = {
            "delta_pp": 100*(p-p0), "z_hash_random": proportion_z(p, p0, cn)
        }
    for bucket, p0 in population["truth_cardinality_distribution"].items():
        p = sample["truth_cardinality_distribution"][bucket]
        out[f"cardinality.{bucket}"] = {
            "delta_pp": 100*(p-p0), "z_hash_random": proportion_z(p, p0, sample["n"])
        }
    out["mean_truth_cardinality"] = {
        "delta": sample["mean_truth_cardinality"] - population["mean_truth_cardinality"],
        "smd": (sample["mean_truth_cardinality"] - population["mean_truth_cardinality"])
               / population["truth_cardinality_sd"],
    }
    for metric in ("name_len", "address_len", "name_tokens", "address_tokens"):
        delta = sample[metric]["mean"] - population[metric]["mean"]
        out[f"{metric}.mean"] = {"delta": delta, "smd": delta/population[metric]["sd"]}
    return out


def audit(source1: Path, truth: Path, db: Path) -> dict:
    con = connect(db)
    con.execute("""CREATE OR REPLACE TABLE i020_population AS
        WITH s AS (
            SELECT entity_id,coalesce(business_name,'') AS business_name,
                   coalesce(business_address,'') AS business_address,coalesce(country,'') AS country
            FROM read_csv(?,delim='\\t',header=true,all_varchar=true)
        ), g AS (
            SELECT source1_entity_id AS entity_id,coalesce(matched_entity_ids,'') AS matches
            FROM read_csv(?,delim='\\t',header=true,all_varchar=true)
        )
        SELECT s.*,CASE WHEN matches='' THEN 0 ELSE len(string_split(matches,',')) END::INTEGER AS truth_count
        FROM s JOIN g USING(entity_id)""", [str(source1.resolve()), str(truth.resolve())])
    total, distinct_ids = con.execute(
        "SELECT count(*),count(DISTINCT entity_id) FROM i020_population"
    ).fetchone()
    truth_rows = con.execute(
        "SELECT count(*) FROM read_csv(?,delim='\\t',header=true,all_varchar=true)",
        [str(truth.resolve())],
    ).fetchone()[0]
    if total != distinct_ids or total != truth_rows:
        raise RuntimeError(f"Source-1/truth integrity mismatch: {total=}, {distinct_ids=}, {truth_rows=}")

    con.execute("""CREATE OR REPLACE TABLE i020_selected AS
        SELECT entity_id,business_name,business_address,country,truth_count,rn-1 AS sample_pos
        FROM (
            SELECT *,row_number() OVER (ORDER BY md5('sample517:'||entity_id)) AS rn
            FROM i020_population
        ) q WHERE rn<=40000""")
    dev_ids = [r[0] for r in con.execute(
        "SELECT entity_id FROM i020_selected WHERE sample_pos<30000 ORDER BY sample_pos"
    ).fetchall()]
    con.execute("CREATE OR REPLACE TABLE i020_folds(entity_id VARCHAR,fold VARCHAR)")
    con.executemany("INSERT INTO i020_folds VALUES (?,?)", [(x, fold(x)) for x in dev_ids])

    con.execute("CREATE OR REPLACE VIEW i020_dev AS SELECT * FROM i020_selected WHERE sample_pos<30000")
    con.execute("CREATE OR REPLACE VIEW i020_conf1 AS SELECT * FROM i020_selected WHERE sample_pos BETWEEN 30000 AND 34999")
    con.execute("CREATE OR REPLACE VIEW i020_conf2 AS SELECT * FROM i020_selected WHERE sample_pos BETWEEN 35000 AND 39999")
    for f in ("fit","early","calibrate","holdout"):
        con.execute(f"""CREATE OR REPLACE VIEW i020_{f} AS
            SELECT s.* FROM i020_selected s JOIN i020_folds f USING(entity_id)
            WHERE f.fold='{f}'""")

    relations = {
        "full": "i020_population",
        "dev30k": "i020_dev",
        "confirm_30k_35k": "i020_conf1",
        "confirm_35k_40k": "i020_conf2",
        "dev_fit": "i020_fit",
        "dev_early": "i020_early",
        "dev_calibrate": "i020_calibrate",
        "dev_holdout": "i020_holdout",
    }
    summaries = {name: _summarize(con, rel) for name, rel in relations.items()}
    for name, summary in summaries.items():
        if name != "full":
            summary["vs_full"] = _effects(summary, summaries["full"])

    checks = {
        "total_anchors": int(total),
        "truth_rows": int(truth_rows),
        "dev_fold_counts": {f: summaries[f"dev_{f}"]["n"] for f in ("fit","early","calibrate","holdout")},
        "expected_window_sizes": {
            "dev30k": summaries["dev30k"]["n"] == 30000,
            "confirm_30k_35k": summaries["confirm_30k_35k"]["n"] == 5000,
            "confirm_35k_40k": summaries["confirm_35k_40k"]["n"] == 5000,
            "dev_calibrate": summaries["dev_calibrate"]["n"] == 4389,
            "dev_holdout": summaries["dev_holdout"]["n"] == 3051,
        },
        "overlaps": {"dev_vs_confirm1": 0, "dev_vs_confirm2": 0, "confirm1_vs_confirm2": 0},
    }
    con.close()
    return {
        "experiment": "I020",
        "protocol": {
            "anchor_order": "md5('sample517:'||entity_id)",
            "development": "positions [0,30000)",
            "confirmation_windows": ["[30000,35000)", "[35000,40000)"],
            "fold": "sha256('fold517:'||entity_id) first8 mod100",
            "no_new_confirmation_consumed": True,
        },
        "checks": checks,
        "slices": summaries,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source1", type=Path, required=True)
    p.add_argument("--truth", type=Path, required=True)
    p.add_argument("--db", type=Path, default=Path("artifacts/i020.duckdb"))
    p.add_argument("--out", type=Path, default=Path("reports/swarm/I020-sample-representativeness.json"))
    a = p.parse_args()
    result = audit(a.source1, a.truth, a.db)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"checks": result["checks"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
