"""Aggregate audit for same-name/different-address source-one hard negatives.

This command intentionally emits aggregate diagnostics only. It uses the identical
normalization expression from ``src/ber/data.py`` and never writes row-level
challenge records to its JSON output.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from itertools import combinations
from pathlib import Path

from .data import connect, rows


def _address_overlap_bands(con) -> dict[str, dict[str, int]]:
    """Exact pairwise token-Jaccard bands inside repeated-name groups."""
    out: dict[str, Counter] = {"ALL": Counter()}
    cur = con.execute("SELECT country,n,a FROM f005_coll ORDER BY country,n,rid")
    current_key = None
    addresses: list[str] = []

    def flush(key, values):
        if key is None or len(values) < 2:
            return
        country = key[0]
        out.setdefault(country, Counter())
        toks = [set(v.split()) if v else set() for v in values]
        for left, right in combinations(toks, 2):
            inter = len(left & right)
            union = len(left | right)
            jaccard = inter / union if union else 1.0
            if inter == 0:
                band = "zero"
            elif jaccard <= 0.25:
                band = "(0,.25]"
            elif jaccard <= 0.50:
                band = "(.25,.50]"
            elif jaccard <= 0.75:
                band = "(.50,.75]"
            else:
                band = "(.75,1]"
            out[country][band] += 1
            out["ALL"][band] += 1

    while True:
        batch = cur.fetchmany(100_000)
        if not batch:
            break
        for country, name, address in batch:
            key = (country, name)
            if current_key is not None and key != current_key:
                flush(current_key, addresses)
                addresses = []
            current_key = key
            addresses.append(address)
    flush(current_key, addresses)
    return {country: dict(counter) for country, counter in out.items()}


def _summary_query(country_expr: str, group_by: str) -> str:
    return f"""SELECT {country_expr} AS country,count(*)::BIGINT AS collision_groups,
        sum(freq)::BIGINT AS collision_rows,sum(pairs)::BIGINT AS collision_pairs,
        sum(different_addr_pairs)::BIGINT AS different_addr_pairs,
        sum(same_nonempty_addr_pairs)::BIGINT AS same_nonempty_addr_pairs,
        sum(empty_addr_pairs)::BIGINT AS empty_addr_pairs,
        sum(num_comparable_pairs)::BIGINT AS num_comparable_pairs,
        sum(num_conflict_pairs)::BIGINT AS num_conflict_pairs,
        coalesce(sum(freq) FILTER (WHERE name_tokens=1),0)::BIGINT AS single_token_collision_rows,
        coalesce(sum(freq) FILTER (WHERE name_compact_len<=8),0)::BIGINT AS short8_collision_rows,
        max(freq)::BIGINT AS max_name_freq
        FROM f005_group_metrics {group_by}"""


def audit(source1: Path, truth: Path | None, output: Path, db: Path) -> dict:
    start = time.time()
    con = connect(db)
    con.execute(r"""CREATE OR REPLACE MACRO norm_f005(s) AS
        trim(regexp_replace(lower(strip_accents(coalesce(s, ''))),
        '[^\p{L}\p{N}]+', ' ', 'g'))""")
    con.execute(
        r"""CREATE OR REPLACE TABLE f005_s1 AS
        SELECT row_number() OVER () AS rid, entity_id, coalesce(country,'') AS country,
               trim(lower(coalesce(business_name,''))) AS raw_lower_name,
               norm_f005(business_name) AS n,
               norm_f005(business_address) AS a,
               regexp_extract(norm_f005(business_address),'[0-9]+') AS first_num
        FROM read_csv(?, delim='\t', header=true, all_varchar=true)""",
        [str(source1.resolve())],
    )
    con.execute("""CREATE OR REPLACE TABLE f005_name_freq AS
        SELECT country,n,count(*)::BIGINT AS freq
        FROM f005_s1 WHERE n<>'' GROUP BY country,n""")
    con.execute("""CREATE OR REPLACE TABLE f005_coll AS
        SELECT s.*,f.freq FROM f005_s1 s JOIN f005_name_freq f USING(country,n)
        WHERE f.freq>1""")
    con.execute("""CREATE OR REPLACE TABLE f005_groups AS
        SELECT country,n,freq,
               len(string_split(n,' '))::BIGINT AS name_tokens,
               len(replace(n,' ',''))::BIGINT AS name_compact_len,
               (freq*(freq-1)/2)::BIGINT AS pairs
        FROM f005_name_freq WHERE freq>1""")
    con.execute("""CREATE OR REPLACE TABLE f005_addr_counts AS
        SELECT country,n,a,count(*)::BIGINT AS c FROM f005_coll GROUP BY country,n,a""")
    con.execute("""CREATE OR REPLACE TABLE f005_addr_pairs AS
        SELECT country,n,
               sum(c*(c-1)/2)::BIGINT AS same_addr_pairs,
               coalesce(sum(c*(c-1)/2) FILTER (WHERE a<>''),0)::BIGINT AS same_nonempty_addr_pairs,
               coalesce(sum(c*(c-1)/2) FILTER (WHERE a=''),0)::BIGINT AS empty_addr_pairs
        FROM f005_addr_counts GROUP BY country,n""")
    con.execute("""CREATE OR REPLACE TABLE f005_num_counts AS
        SELECT country,n,first_num,count(*)::BIGINT AS c
        FROM f005_coll WHERE first_num<>'' GROUP BY country,n,first_num""")
    con.execute("""CREATE OR REPLACE TABLE f005_num_pairs AS
        SELECT country,n,sum(c)::BIGINT AS num_rows,
               sum(c*(c-1)/2)::BIGINT AS same_num_pairs
        FROM f005_num_counts GROUP BY country,n""")
    con.execute("""CREATE OR REPLACE TABLE f005_group_metrics AS
        SELECT g.*,
               coalesce(a.same_addr_pairs,0)::BIGINT AS same_addr_pairs,
               coalesce(a.same_nonempty_addr_pairs,0)::BIGINT AS same_nonempty_addr_pairs,
               coalesce(a.empty_addr_pairs,0)::BIGINT AS empty_addr_pairs,
               (g.pairs-coalesce(a.same_addr_pairs,0))::BIGINT AS different_addr_pairs,
               coalesce(p.num_rows,0)::BIGINT AS num_rows,
               (coalesce(p.num_rows,0)*(coalesce(p.num_rows,0)-1)/2)::BIGINT AS num_comparable_pairs,
               coalesce(p.same_num_pairs,0)::BIGINT AS same_num_pairs,
               ((coalesce(p.num_rows,0)*(coalesce(p.num_rows,0)-1)/2)-coalesce(p.same_num_pairs,0))::BIGINT AS num_conflict_pairs
        FROM f005_groups g
        LEFT JOIN f005_addr_pairs a USING(country,n)
        LEFT JOIN f005_num_pairs p USING(country,n)""")

    source_rows = {r[0]: int(r[1]) for r in con.execute(
        "SELECT country,count(*) FROM f005_s1 GROUP BY country ORDER BY country"
    ).fetchall()}
    summary = rows(con, _summary_query("country", "GROUP BY country ORDER BY country"))
    summary.insert(0, rows(con, _summary_query("'ALL'", ""))[0])
    for r in summary:
        denom = sum(source_rows.values()) if r["country"] == "ALL" else source_rows[r["country"]]
        r["source1_rows"] = denom
        r["collision_row_rate"] = r["collision_rows"] / denom
        r["number_conflict_rate_when_comparable"] = (
            r["num_conflict_pairs"] / r["num_comparable_pairs"] if r["num_comparable_pairs"] else None
        )

    freq_bins = rows(con, """WITH b AS (
        SELECT country,
          CASE WHEN freq=2 THEN '2' WHEN freq<=5 THEN '3-5' WHEN freq<=20 THEN '6-20'
               WHEN freq<=100 THEN '21-100' ELSE '>100' END AS freq_bin,
          freq,pairs,different_addr_pairs,num_conflict_pairs FROM f005_group_metrics)
        SELECT country,freq_bin,count(*)::BIGINT AS groups,sum(freq)::BIGINT AS rows,
               sum(pairs)::BIGINT AS pairs,sum(different_addr_pairs)::BIGINT AS different_addr_pairs,
               sum(num_conflict_pairs)::BIGINT AS num_conflict_pairs
        FROM b GROUP BY country,freq_bin
        UNION ALL
        SELECT 'ALL',freq_bin,count(*)::BIGINT,sum(freq)::BIGINT,sum(pairs)::BIGINT,
               sum(different_addr_pairs)::BIGINT,sum(num_conflict_pairs)::BIGINT
        FROM b GROUP BY freq_bin
        ORDER BY country,freq_bin""")

    raw_collision = rows(con, """WITH f AS (
        SELECT country,raw_lower_name,count(*)::BIGINT freq FROM f005_s1
        WHERE raw_lower_name<>'' GROUP BY country,raw_lower_name)
        SELECT sum(freq)::BIGINT AS collision_rows,count(*)::BIGINT AS collision_groups,
               max(freq)::BIGINT AS max_freq FROM f WHERE freq>1""")[0]
    raw_collision["collision_row_rate"] = raw_collision["collision_rows"] / sum(source_rows.values())

    singleton = []
    if truth is not None:
        con.execute("""CREATE OR REPLACE TABLE f005_truth AS
            SELECT source1_entity_id AS anchor,coalesce(matched_entity_ids,'') AS matches
            FROM read_csv(?, delim='\t', header=true, all_varchar=true)""", [str(truth.resolve())])
        singleton = rows(con, """WITH x AS (
            SELECT s.country,CASE WHEN t.matches='' THEN 'singleton' ELSE 'non_singleton' END AS class,
                   coalesce(f.freq,0)>1 AS collision
            FROM f005_s1 s JOIN f005_truth t ON s.entity_id=t.anchor
            LEFT JOIN f005_name_freq f USING(country,n))
            SELECT country,class,count(*)::BIGINT AS rows,
                   count(*) FILTER (WHERE collision)::BIGINT AS collision_rows
            FROM x GROUP BY country,class
            UNION ALL
            SELECT 'ALL',class,count(*)::BIGINT,
                   count(*) FILTER (WHERE collision)::BIGINT
            FROM x GROUP BY class ORDER BY country,class""")
        for r in singleton:
            r["collision_rate"] = r["collision_rows"] / r["rows"] if r["rows"] else None

    result = {
        "protocol": {
            "source1": str(source1),
            "truth": str(truth) if truth else None,
            "normalization": "identical expression to src/ber/data.py norm macro",
            "source1_bytes": source1.stat().st_size,
            "truth_bytes": truth.stat().st_size if truth else None,
        },
        "summary": summary,
        "raw_lower_trim_collision": raw_collision,
        "frequency_bins": freq_bins,
        "address_token_jaccard_bands": _address_overlap_bands(con),
        "singleton_by_country": singleton,
        "elapsed_seconds": time.time() - start,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    con.close()
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source1", type=Path, required=True)
    p.add_argument("--truth", type=Path)
    p.add_argument("--output", type=Path, default=Path("artifacts/f005_common_name_audit.json"))
    p.add_argument("--db", type=Path, default=Path(":memory:"))
    args = p.parse_args()
    print(json.dumps(audit(args.source1, args.truth, args.output, args.db), indent=2))


if __name__ == "__main__":
    main()
