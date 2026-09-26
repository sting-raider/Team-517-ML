import sys
import types
import unittest
from unittest.mock import patch

if "duckdb" not in sys.modules:
    try:
        import duckdb  # noqa: F401
    except ModuleNotFoundError:
        sys.modules["duckdb"] = types.SimpleNamespace(connect=None)
if "catboost" not in sys.modules:
    try:
        import catboost  # noqa: F401
    except ModuleNotFoundError:
        sys.modules["catboost"] = types.SimpleNamespace(CatBoostClassifier=object)

from ber.provenance import fingerprint
from ber.retrieval_v3 import (
    CHAR_GRAM_MACRO_SQL,
    CHAR_INDEX_MAX_FREQ,
    CHAR_INVENTORY_COLUMNS,
    build_char_index,
    char_index_identity,
)


class _Result:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = [] if many is None else many

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _IdentityConnection:
    def __init__(self, relation_row):
        self.relation_row = relation_row

    def execute(self, sql, params=None):
        if "SELECT count(*)::UBIGINT" in sql:
            return _Result(one=self.relation_row)
        raise AssertionError(f"unexpected SQL in identity test: {sql}")


class _CacheConnection:
    def __init__(self, tables=(), stored=None):
        self.tables = set(tables)
        self.stored = stored
        self.statements = []

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.statements.append((normalized, params))
        if "SELECT table_name FROM information_schema.tables" in normalized:
            return _Result(many=[(name,) for name in sorted(self.tables)])
        if normalized.startswith("SELECT fingerprint FROM char_index_signatures"):
            return _Result(one=(self.stored,) if self.stored is not None else None)
        if normalized.startswith("DELETE FROM char_index_signatures"):
            self.stored = None
        if normalized.startswith("INSERT INTO char_index_signatures"):
            self.stored = params[1]
        return _Result()

    def rebuilt_raw_table(self):
        return any(
            "CREATE OR REPLACE TABLE train_char_raw" in sql
            for sql, _ in self.statements
        )


class _CrashOnIndexRebuildConnection(_CacheConnection):
    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        if "CREATE OR REPLACE TABLE train_char_index" in normalized:
            self.statements.append((normalized, params))
            raise RuntimeError("simulated rebuild interruption")
        return super().execute(sql, params)


class V3CharacterCacheProvenanceTests(unittest.TestCase):
    def test_identity_is_stable_and_binds_inventory(self):
        first = char_index_identity(_IdentityConnection((7, 11, 13)), "train")
        second = char_index_identity(_IdentityConnection((7, 11, 13)), "train")
        changed = char_index_identity(_IdentityConnection((7, 12, 13)), "train")
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertEqual(first["max_frequency"], CHAR_INDEX_MAX_FREQ)
        self.assertEqual(first["gram_macro_sql"], CHAR_GRAM_MACRO_SQL)
        self.assertEqual(first["inventory"]["columns"], list(CHAR_INVENTORY_COLUMNS))

    def test_compatible_signed_index_reuses_without_rebuild(self):
        identity = {"kind": "test-char-index", "inventory": {"rows": 7}}
        expected = fingerprint(identity)
        c = _CacheConnection(
            tables={"train_char_freq", "train_char_index"},
            stored=expected,
        )
        with patch("ber.retrieval_v3.char_index_identity", return_value=identity):
            actual = build_char_index(c, "train")
        self.assertEqual(actual, expected)
        self.assertFalse(c.rebuilt_raw_table())

    def test_unsigned_or_mismatched_index_rebuilds(self):
        identity = {"kind": "test-char-index", "inventory": {"rows": 7}}
        expected = fingerprint(identity)
        for stored in (None, "stale"):
            with self.subTest(stored=stored):
                c = _CacheConnection(
                    tables={"train_char_freq", "train_char_index"},
                    stored=stored,
                )
                with patch("ber.retrieval_v3.char_index_identity", return_value=identity):
                    actual = build_char_index(c, "train")
                self.assertEqual(actual, expected)
                self.assertTrue(c.rebuilt_raw_table())
                self.assertEqual(c.stored, expected)

    def test_partial_cache_rebuilds_even_with_matching_signature(self):
        identity = {"kind": "test-char-index", "inventory": {"rows": 7}}
        expected = fingerprint(identity)
        c = _CacheConnection(tables={"train_char_index"}, stored=expected)
        with patch("ber.retrieval_v3.char_index_identity", return_value=identity):
            build_char_index(c, "train")
        self.assertTrue(c.rebuilt_raw_table())

    def test_partial_rebuild_clears_signature_before_mutation(self):
        identity = {"kind": "test-char-index", "inventory": {"rows": 7}}
        expected = fingerprint(identity)
        c = _CrashOnIndexRebuildConnection(
            tables={"train_char_index"},
            stored=expected,
        )
        with patch("ber.retrieval_v3.char_index_identity", return_value=identity):
            with self.assertRaisesRegex(RuntimeError, "simulated rebuild interruption"):
                build_char_index(c, "train")
        self.assertIsNone(c.stored)
        delete_index = next(
            i for i, (sql, _) in enumerate(c.statements)
            if sql.startswith("DELETE FROM char_index_signatures")
        )
        crash_index = next(
            i for i, (sql, _) in enumerate(c.statements)
            if "CREATE OR REPLACE TABLE train_char_index" in sql
        )
        self.assertLess(delete_index, crash_index)


if __name__ == "__main__":
    unittest.main()
