"""Opt-in numeric-token document-frequency evidence for matcher experiments.

The frozen INT003/V3 path is unchanged. These helpers build split-local,
country-local numeric-token document frequencies. Source 1 frequencies are
scoped by country; target-side frequencies are additionally scoped by the
actual target source (S2 versus S3) so one target inventory cannot inflate the
other's commonness signal. Numeric tokens are deduplicated per record before
DF counting so repeated address numbers do not inflate commonness.
"""
import math


NUMBER_COMMONNESS_NAMES = [
    f"{field}_{name}"
    for field in ("name", "address")
    for name in (
        "shared_number_left_log_df",
        "shared_number_right_log_df",
        "left_only_number_log_df",
        "right_only_number_log_df",
    )
]


def _checked_split(split):
    if split not in ("train", "test"):
        raise ValueError("split must be train or test")
    return split


def _table(split, side, field, suffix):
    split = _checked_split(split)
    if side not in ("left", "right") or field not in ("n", "a"):
        raise ValueError("invalid number-commonness table key")
    return f"m003_{split}_{side}_{field}_{suffix}"


def commonness_values(left_numbers, right_numbers, left_df, right_df):
    """Reference semantics for one field.

    Returns shared-token commonness from each inventory side, followed by
    commonness of unmatched tokens on the left and right. Lower positive values
    mean rarer observed tokens because the feature is log(1 + minimum DF).
    Zero means that the corresponding token set is empty; existing V3
    number-overlap/conflict features disambiguate absence from actual
    agreement/conflict.
    """
    left = set(left_numbers)
    right = set(right_numbers)

    def log_min(tokens, freq):
        values = [freq[t] for t in tokens if t in freq]
        return math.log1p(min(values)) if values else 0.0

    shared = left & right
    return [
        log_min(shared, left_df),
        log_min(shared, right_df),
        log_min(left - right, left_df),
        log_min(right - left, right_df),
    ]


def build_number_commonness(c, split):
    """Build split-local token-DF and normalized-value profile tables.

    Left/source-one tables are keyed by country. Right/target tables are keyed
    by country and concrete target source so S2 and S3 retain independent
    document-frequency evidence.
    """
    split = _checked_split(split)
    for side, condition in (("left", "s.source=1"), ("right", "s.source>1")):
        for field in ("n", "a"):
            df_table = _table(split, side, field, "df")
            profile_table = _table(split, side, field, "profile")
            if side == "left":
                c.execute(f"""
                    CREATE OR REPLACE TABLE {df_table} AS
                    WITH docs AS (
                        SELECT s.country,s.rowid AS rid,u.token
                        FROM {split} s,
                        unnest(list_distinct(regexp_extract_all(s.{field}, '[0-9]+'))) u(token)
                        WHERE {condition} AND s.{field}<>'' AND u.token<>''
                    )
                    SELECT country,token,count(*)::INTEGER AS freq
                    FROM docs GROUP BY country,token
                """)
                c.execute(f"""
                    CREATE OR REPLACE TABLE {profile_table} AS
                    WITH values AS (
                        SELECT DISTINCT s.country,s.{field} AS value,u.token
                        FROM {split} s,
                        unnest(list_distinct(regexp_extract_all(s.{field}, '[0-9]+'))) u(token)
                        WHERE {condition} AND s.{field}<>'' AND u.token<>''
                    )
                    SELECT v.country,v.value,
                        list(v.token ORDER BY v.token) AS tokens,
                        list(d.freq ORDER BY v.token) AS dfs
                    FROM values v
                    JOIN {df_table} d USING(country,token)
                    GROUP BY v.country,v.value
                """)
            else:
                c.execute(f"""
                    CREATE OR REPLACE TABLE {df_table} AS
                    WITH docs AS (
                        SELECT s.country,s.source,s.rowid AS rid,u.token
                        FROM {split} s,
                        unnest(list_distinct(regexp_extract_all(s.{field}, '[0-9]+'))) u(token)
                        WHERE {condition} AND s.{field}<>'' AND u.token<>''
                    )
                    SELECT country,source,token,count(*)::INTEGER AS freq
                    FROM docs GROUP BY country,source,token
                """)
                c.execute(f"""
                    CREATE OR REPLACE TABLE {profile_table} AS
                    WITH values AS (
                        SELECT DISTINCT s.country,s.source,s.{field} AS value,u.token
                        FROM {split} s,
                        unnest(list_distinct(regexp_extract_all(s.{field}, '[0-9]+'))) u(token)
                        WHERE {condition} AND s.{field}<>'' AND u.token<>''
                    )
                    SELECT v.country,v.source,v.value,
                        list(v.token ORDER BY v.token) AS tokens,
                        list(d.freq ORDER BY v.token) AS dfs
                    FROM values v
                    JOIN {df_table} d USING(country,source,token)
                    GROUP BY v.country,v.source,v.value
                """)


def profile_joins(split, left_alias="l", right_alias="r"):
    """SQL joins for the four normalized-value number profiles."""
    split = _checked_split(split)
    return "\n".join([
        f"LEFT JOIN {_table(split,'left','n','profile')} m003_ln ON "
        f"m003_ln.country={left_alias}.country AND m003_ln.value={left_alias}.n",
        f"LEFT JOIN {_table(split,'right','n','profile')} m003_rn ON "
        f"m003_rn.country={right_alias}.country AND m003_rn.source={right_alias}.source "
        f"AND m003_rn.value={right_alias}.n",
        f"LEFT JOIN {_table(split,'left','a','profile')} m003_la ON "
        f"m003_la.country={left_alias}.country AND m003_la.value={left_alias}.a",
        f"LEFT JOIN {_table(split,'right','a','profile')} m003_ra ON "
        f"m003_ra.country={right_alias}.country AND m003_ra.source={right_alias}.source "
        f"AND m003_ra.value={right_alias}.a",
    ])


def _tokens(alias):
    return f"coalesce({alias}.tokens,[]::VARCHAR[])"


def _log_min_df(alias, subset):
    return (
        "coalesce(ln(1+list_min(list_transform("
        f"{subset},x->list_extract({alias}.dfs,list_position({alias}.tokens,x))"
        "))),0.0)"
    )


def _field_expressions(left_profile, right_profile):
    left = _tokens(left_profile)
    right = _tokens(right_profile)
    shared = f"list_intersect({left},{right})"
    left_only = f"list_filter({left},x->NOT list_contains({right},x))"
    right_only = f"list_filter({right},x->NOT list_contains({left},x))"
    return [
        _log_min_df(left_profile, shared),
        _log_min_df(right_profile, shared),
        _log_min_df(left_profile, left_only),
        _log_min_df(right_profile, right_only),
    ]


def select_expressions():
    """Return SQL expressions in NUMBER_COMMONNESS_NAMES order."""
    return _field_expressions("m003_ln", "m003_rn") + _field_expressions("m003_la", "m003_ra")
