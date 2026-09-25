"""Full Source-1 country/normalization shift audit using supplied challenge TSVs only.

This utility intentionally does not read S2/S3 or labels. It quantifies raw-text and
normalization distributions plus a Source-1-only token-frequency proxy for one focus
country. The proxy is diagnostic only: blocker frequency thresholds are computed on
S2/S3 in production and therefore must not be treated as candidate-recall evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


NORMALIZER_SQL = r"""
CREATE OR REPLACE MACRO norm_x(s) AS
  trim(regexp_replace(lower(strip_accents(coalesce(s, ''))),
                      '[^\\p{L}\\p{N}]+', ' ', 'g'));
CREATE OR REPLACE MACRO folded_x(s) AS lower(strip_accents(coalesce(s, '')));
"""

ADDRESS_STOP = (
    "road", "street", "avenue", "drive", "lane", "floor", "near",
    "opposite", "the", "and", "unit", "plot", "no",
)


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params=None) -> list[dict]:
    cur = con.execute(sql, params or [])
    names = [x[0] for x in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _make_view(con: duckdb.DuckDBPyConnection, name: str, path: Path) -> None:
    con.execute(
        f"""CREATE OR REPLACE TEMP VIEW {name} AS
        SELECT coalesce(entity_id,'') entity_id,
               coalesce(business_name,'') business_name,
               coalesce(business_address,'') business_address,
               coalesce(country,'') country
        FROM read_csv(?, delim='\\t', header=true, all_varchar=true)""",
        [str(path.resolve())],
    )


def _field_stats(con: duckdb.DuckDBPyConnection, view: str, field: str) -> list[dict]:
    # RE2-compatible patterns only; no lookbehind.
    return _rows(
        con,
        f"""SELECT country,
            count(*)::BIGINT AS rows,
            avg(length({field})) AS avg_raw_len,
            quantile_disc(length({field}), 0.5) AS raw_len_p50,
            quantile_disc(length({field}), 0.9) AS raw_len_p90,
            quantile_disc(length({field}), 0.99) AS raw_len_p99,
            avg(length(norm_x({field}))) AS avg_norm_len,
            quantile_disc(CASE WHEN norm_x({field})='' THEN 0
                               ELSE len(string_split(norm_x({field}),' ')) END, 0.5) AS token_p50,
            quantile_disc(CASE WHEN norm_x({field})='' THEN 0
                               ELSE len(string_split(norm_x({field}),' ')) END, 0.9) AS token_p90,
            avg(({field}='')::INT) AS empty_rate,
            avg(regexp_matches({field}, '[^\\x00-\\x7F]')::INT) AS nonascii_rate,
            avg((folded_x({field})<>lower({field}))::INT) AS accent_changed_rate,
            avg((norm_x({field})<>lower(trim({field})))::INT) AS norm_diff_rate,
            avg(regexp_matches({field}, '[0-9]')::INT) AS digit_rate,
            avg(regexp_matches({field}, '[''’]')::INT) AS apostrophe_rate,
            avg(regexp_matches({field}, '[-‐‑‒–—]')::INT) AS hyphen_rate,
            avg(regexp_matches({field}, ',')::INT) AS comma_rate,
            avg(regexp_matches({field}, '&')::INT) AS ampersand_rate
        FROM {view} GROUP BY country ORDER BY country""",
    )


def _address_shapes(con: duckdb.DuckDBPyConnection, view: str) -> list[dict]:
    return _rows(
        con,
        f"""SELECT country, count(*)::BIGINT AS rows,
            avg(regexp_matches(business_address,
                '(^|[^0-9])[0-9]{{5}}([^0-9]|$)')::INT) AS five_digit_token_rate,
            avg(regexp_matches(business_address,
                '(^|[^0-9])[0-9]{{6}}([^0-9]|$)')::INT) AS six_digit_token_rate,
            avg(regexp_matches(business_address, '^[[:space:]]*[0-9]+')::INT)
                AS leading_number_rate
        FROM {view} GROUP BY country ORDER BY country""",
    )


def _collision_stats(
    con: duckdb.DuckDBPyConnection, view: str, country: str, field: str
) -> dict:
    # This is corpus-format information loss, not an entity-error metric.
    base = f"FROM {view} WHERE country=?"
    raw_distinct = con.execute(
        f"SELECT count(DISTINCT lower(trim({field}))) {base}", [country]
    ).fetchone()[0]
    norm_distinct = con.execute(
        f"SELECT count(DISTINCT norm_x({field})) {base}", [country]
    ).fetchone()[0]
    collision_keys = con.execute(
        f"""WITH pairs AS (
              SELECT DISTINCT lower(trim({field})) raw, norm_x({field}) normalized
              {base}
            )
            SELECT count(*) FROM (
              SELECT normalized FROM pairs GROUP BY normalized HAVING count(*)>1
            )""",
        [country],
    ).fetchone()[0]
    collision_rows = con.execute(
        f"""WITH pairs AS (
              SELECT DISTINCT lower(trim({field})) raw, norm_x({field}) normalized
              {base}
            ), bad AS (
              SELECT normalized FROM pairs GROUP BY normalized HAVING count(*)>1
            )
            SELECT count(*) FROM {view} v JOIN bad b
              ON norm_x(v.{field})=b.normalized WHERE v.country=?""",
        [country, country],
    ).fetchone()[0]
    total = con.execute(f"SELECT count(*) {base}", [country]).fetchone()[0]
    return {
        "rows": total,
        "distinct_lower_raw": raw_distinct,
        "distinct_current_norm": norm_distinct,
        "distinct_loss": raw_distinct - norm_distinct,
        "collision_keys": collision_keys,
        "rows_on_collision_keys": collision_rows,
        "collision_row_rate": collision_rows / total if total else 0.0,
    }


def _focus_token_proxy(
    con: duckdb.DuckDBPyConnection, view: str, country: str, threshold: int
) -> dict:
    stop = ",".join("'" + x.replace("'", "''") + "'" for x in ADDRESS_STOP)
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE focus AS
        SELECT row_number() OVER () AS rid, norm_x(business_name) n,
               norm_x(business_address) a
        FROM {view} WHERE country=?""",
        [country],
    )
    con.execute(
        """CREATE OR REPLACE TEMP TABLE focus_name_tokens AS
        SELECT DISTINCT rid, tok FROM focus, unnest(string_split(n,' ')) u(tok)
        WHERE len(tok)>=3"""
    )
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE focus_address_tokens AS
        SELECT DISTINCT rid, tok FROM focus, unnest(string_split(a,' ')) u(tok)
        WHERE len(tok)>=3 AND NOT regexp_full_match(tok,'[0-9]+')
          AND tok NOT IN ({stop})"""
    )

    result = {}
    for kind in ("name", "address"):
        table = f"focus_{kind}_tokens"
        top = _rows(
            con,
            f"""SELECT tok AS token, count(*)::BIGINT AS source1_df
            FROM {table} GROUP BY tok ORDER BY source1_df DESC, tok LIMIT 40""",
        )
        counts = _rows(
            con,
            f"""WITH freq AS (
                  SELECT tok, count(*) df FROM {table} GROUP BY tok
                ), per_row AS (
                  SELECT rid, count(*) FILTER (WHERE f.df<=?) AS rare_tokens
                  FROM {table} t JOIN freq f USING(tok) GROUP BY rid
                ), all_rows AS (
                  SELECT f.rid, coalesce(p.rare_tokens,0) rare_tokens
                  FROM focus f LEFT JOIN per_row p USING(rid)
                )
                SELECT count(*)::BIGINT rows,
                       avg((rare_tokens=0)::INT) zero_rare_rate,
                       avg((rare_tokens>=1)::INT) at_least_1_rare_rate,
                       avg((rare_tokens>=2)::INT) at_least_2_rare_rate,
                       avg((rare_tokens>=4)::INT) at_least_4_rare_rate,
                       avg(rare_tokens) mean_rare_tokens
                FROM all_rows""",
            [threshold],
        )[0]
        result[kind] = {"threshold": threshold, "top_tokens": top, "proxy": counts}
    return result


def audit(train: Path, test: Path, out: Path, focus_country: str, df_threshold: int) -> None:
    con = duckdb.connect(":memory:")
    con.execute("SET preserve_insertion_order=false")
    con.execute(NORMALIZER_SQL)
    _make_view(con, "train_s1", train)
    _make_view(con, "test_s1", test)

    result = {
        "scope": "complete Source-1 train/test files; supplied challenge records only",
        "normalizer": "same lower+strip_accents+Unicode-letter/number normalization as src/ber/data.py",
        "train": {
            "name": _field_stats(con, "train_s1", "business_name"),
            "address": _field_stats(con, "train_s1", "business_address"),
            "address_shapes": _address_shapes(con, "train_s1"),
        },
        "test": {
            "name": _field_stats(con, "test_s1", "business_name"),
            "address": _field_stats(con, "test_s1", "business_address"),
            "address_shapes": _address_shapes(con, "test_s1"),
        },
        "focus_country": focus_country,
        "focus_collisions": {
            "name": _collision_stats(con, "test_s1", focus_country, "business_name"),
            "address": _collision_stats(con, "test_s1", focus_country, "business_address"),
        },
        "focus_source1_df_proxy": _focus_token_proxy(
            con, "test_s1", focus_country, df_threshold
        ),
        "proxy_warning": (
            "Source-1 token document frequency is not the blocker frequency. Production blocker "
            "frequency is measured on S2/S3; this proxy is format diagnostics only."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    con.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train-source1", type=Path, required=True)
    p.add_argument("--test-source1", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("reports/swarm/X007-source1-france-shift.json"))
    p.add_argument("--focus-country", default="France")
    p.add_argument("--df-threshold", type=int, default=1000)
    a = p.parse_args()
    audit(a.train_source1, a.test_source1, a.out, a.focus_country, a.df_threshold)


if __name__ == "__main__":
    main()
