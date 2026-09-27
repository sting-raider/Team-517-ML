"""Corpus-IDF primitives for opt-in pair similarity features.

Profiles are built only from supplied normalized challenge records. They are
split-local and source-local so training and inference use the same semantics
without mixing S2 and S3 document frequencies.
"""
from __future__ import annotations

import math
import re

IDF_VERSION = 1
IDF_FEATURE_NAMES = [
    f"{field}_idf_{metric}"
    for field in ("name", "address")
    for metric in ("jaccard", "overlap", "left_coverage", "right_coverage")
]

_VALID_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(value: str) -> str:
    if not _VALID_TABLE.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def idf_weight(rows: int, df: int) -> float:
    """Smoothed positive IDF used by both SQL and reference tests."""
    if rows < 0 or df < 0 or df > rows:
        raise ValueError("invalid rows/df")
    return math.log((rows + 1.0) / (df + 1.0)) + 1.0


def pair_token_weight(left_rows: int, left_df: int, right_rows: int, right_df: int) -> float:
    """Symmetric mean of side-local IDFs for one token."""
    return 0.5 * (idf_weight(left_rows, left_df) + idf_weight(right_rows, right_df))


def weighted_overlap(left: set[str], right: set[str], weights: dict[str, float]) -> tuple[float, float, float, float]:
    """Weighted Jaccard, overlap, left coverage, and right coverage."""
    left, right = set(left), set(right)
    union = left | right
    if not union:
        return 0.0, 0.0, 0.0, 0.0

    def mass(values: set[str]) -> float:
        total = 0.0
        for token in values:
            weight = float(weights[token])
            if not math.isfinite(weight) or weight <= 0:
                raise ValueError("token weights must be finite and positive")
            total += weight
        return total

    inter = left & right
    wi, wu, wl, wr = mass(inter), mass(union), mass(left), mass(right)
    return (
        wi / wu if wu else 0.0,
        wi / min(wl, wr) if min(wl, wr) else 0.0,
        wi / wl if wl else 0.0,
        wi / wr if wr else 0.0,
    )


def table_names(split: str) -> tuple[str, str, str]:
    split = _safe_identifier(split)
    return (f"m001_idf_profile_{split}", f"m001_idf_token_{split}", f"m001_idf_meta_{split}")


def build_token_idf_tables(c, split: str) -> dict:
    """Materialize source/country/field-local token DF and IDF tables."""
    split = _safe_identifier(split)
    profile, token_table, meta = table_names(split)
    c.execute(f"""CREATE OR REPLACE TABLE {profile} AS
        SELECT source,country,count(*)::BIGINT AS nrows
        FROM {split} GROUP BY source,country""")
    c.execute(f"""CREATE OR REPLACE TABLE {token_table} AS
        WITH tokens AS (
            SELECT source,country,'name' AS field,rowid,
                unnest(list_distinct(string_split(n,' '))) AS token
            FROM {split} WHERE n<>''
            UNION ALL
            SELECT source,country,'address' AS field,rowid,
                unnest(list_distinct(string_split(a,' '))) AS token
            FROM {split} WHERE a<>''
        )
        SELECT t.source,t.country,t.field,t.token,count(*)::BIGINT AS df,
            ln((p.nrows+1.0)/(count(*)+1.0))+1.0 AS idf
        FROM tokens t JOIN {profile} p USING(source,country)
        WHERE t.token<>''
        GROUP BY t.source,t.country,t.field,t.token,p.nrows""")
    c.execute(f"""CREATE OR REPLACE TABLE {meta} AS
        SELECT {IDF_VERSION}::INTEGER AS version,count(*)::BIGINT AS source_rows
        FROM {split}""")
    source_rows = c.execute(f"SELECT source_rows FROM {meta}").fetchone()[0]
    profiles = c.execute(f"SELECT count(*) FROM {profile}").fetchone()[0]
    tokens = c.execute(f"SELECT count(*) FROM {token_table}").fetchone()[0]
    return {"version": IDF_VERSION, "source_rows": source_rows, "profiles": profiles, "tokens": tokens}


def ensure_token_idf_tables(c, split: str) -> dict:
    """Fail closed when a prepared inference DB lacks current IDF profiles."""
    split = _safe_identifier(split)
    profile, token_table, meta = table_names(split)
    expected = {profile, token_table, meta}
    found = {
        row[0]
        for row in c.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name IN (?,?,?)",
            [profile, token_table, meta],
        ).fetchall()
    }
    if found != expected:
        raise ValueError(f"Missing M001 IDF tables for {split}; rebuild the prepared database")
    version, recorded_rows = c.execute(f"SELECT version,source_rows FROM {meta}").fetchone()
    actual_rows = c.execute(f"SELECT count(*) FROM {split}").fetchone()[0]
    if version != IDF_VERSION or recorded_rows != actual_rows:
        raise ValueError("Stale M001 IDF profile metadata; rebuild the prepared database")
    return {
        "version": version,
        "source_rows": recorded_rows,
        "profiles": c.execute(f"SELECT count(*) FROM {profile}").fetchone()[0],
        "tokens": c.execute(f"SELECT count(*) FROM {token_table}").fetchone()[0],
    }
