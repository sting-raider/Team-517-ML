import csv
import gzip
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

try:
    import duckdb
except ImportError:
    duckdb = None

from ber.candidate_cache import (
    export_candidate_cache,
    import_candidate_cache,
    validate_candidate_cache,
)


def stable_rows(connection, table):
    return connection.execute(f'''SELECT c.anchor,t.entity_id,c.retrieval,c.hits
        FROM {table} c JOIN train t ON c.rid=t.rowid
        ORDER BY c.anchor,c.retrieval DESC,t.entity_id''').fetchall()


class CandidateCacheTests(unittest.TestCase):
    def make_db(self, target_order=("s2_b", "s2_a", "s3_c")):
        c = sqlite3.connect(":memory:")
        c.execute("CREATE TABLE train(entity_id TEXT, source INTEGER)")
        c.executemany("INSERT INTO train VALUES (?,1)", [("a1",), ("a2",)])
        sources = {"s2_a": 2, "s2_b": 2, "s3_c": 3}
        c.executemany("INSERT INTO train VALUES (?,?)", [(x, sources[x]) for x in target_order])
        c.execute("CREATE TABLE anchors AS SELECT * FROM train WHERE source=1")
        return c

    def make_candidates(self, c):
        c.execute("CREATE TABLE candidates(anchor TEXT,rid INTEGER,retrieval REAL,hits INTEGER)")
        ids = dict(c.execute("SELECT entity_id,rowid FROM train").fetchall())
        c.executemany("INSERT INTO candidates VALUES (?,?,?,?)", [
            ("a1", ids["s2_a"], 9.5, 2),
            ("a1", ids["s3_c"], 8.0, 1),
            ("a2", ids["s2_b"], 7.0, 3),
        ])

    @unittest.skipUnless(duckdb is not None, "duckdb not installed")
    def test_duckdb_vectorized_import_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.csv.gz"
            source = duckdb.connect()
            source.execute("CREATE TABLE train(entity_id VARCHAR, source INTEGER)")
            source.executemany("INSERT INTO train VALUES (?,1)", [("a1",), ("a2",)])
            source.executemany("INSERT INTO train VALUES (?,?)", [("s2_b", 2), ("s2_a", 2), ("s3_c", 3)])
            source.execute("CREATE TABLE anchors AS SELECT * FROM train WHERE source=1")
            self.make_candidates(source)
            expected = stable_rows(source, "candidates")
            export_candidate_cache(
                source, path, split="train", anchor_table="anchors",
                candidate_table="candidates", candidate_cap=2,
            )

            target = duckdb.connect()
            target.execute("CREATE TABLE train(entity_id VARCHAR, source INTEGER)")
            target.executemany("INSERT INTO train VALUES (?,1)", [("a1",), ("a2",)])
            target.executemany("INSERT INTO train VALUES (?,?)", [("s3_c", 3), ("s2_a", 2), ("s2_b", 2)])
            target.execute("CREATE TABLE anchors AS SELECT * FROM train WHERE source=1")
            import_candidate_cache(
                target, path, anchor_table="anchors", result_table="restored",
                expected_split="train", expected_cap=2,
            )
            self.assertEqual(expected, stable_rows(target, "restored"))
            source.close()
            target.close()

    def test_round_trip_survives_changed_rowids(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.csv.gz"
            source = self.make_db()
            self.make_candidates(source)
            expected = stable_rows(source, "candidates")
            manifest = export_candidate_cache(
                source, path, split="train", anchor_table="anchors",
                candidate_table="candidates", candidate_cap=2,
                provenance={"experiment": "synthetic"}, batch_size=2,
            )
            self.assertEqual(manifest["row_count"], 3)
            self.assertEqual(manifest["anchor_count"], 2)
            self.assertEqual(manifest["max_rank"], 2)

            target = self.make_db(("s3_c", "s2_a", "s2_b"))
            before = dict(target.execute("SELECT entity_id,rowid FROM train").fetchall())
            source_ids = dict(source.execute("SELECT entity_id,rowid FROM train").fetchall())
            self.assertNotEqual(before["s2_b"], source_ids["s2_b"])
            import_candidate_cache(
                target, path, anchor_table="anchors", result_table="restored",
                expected_split="train", expected_cap=2, batch_size=2,
            )
            self.assertEqual(expected, stable_rows(target, "restored"))

    def test_checksum_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.csv.gz"
            c = self.make_db()
            self.make_candidates(c)
            export_candidate_cache(
                c, path, split="train", anchor_table="anchors",
                candidate_table="candidates", candidate_cap=2,
            )
            with path.open("ab") as f:
                f.write(b"corruption")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                validate_candidate_cache(path)

    def test_duplicate_pair_with_valid_checksum_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.csv.gz"
            c = self.make_db()
            self.make_candidates(c)
            export_candidate_cache(
                c, path, split="train", anchor_table="anchors",
                candidate_table="candidates", candidate_cap=2,
            )
            with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))
            rows[2][1] = rows[1][1]
            with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
                csv.writer(f, lineterminator="\n").writerows(rows)
            mpath = path.with_name(path.name + ".manifest.json")
            manifest = json.loads(mpath.read_text())
            manifest["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            mpath.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Duplicate candidate pair"):
                validate_candidate_cache(path)

    def test_expected_cap_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.csv.gz"
            c = self.make_db()
            self.make_candidates(c)
            export_candidate_cache(
                c, path, split="train", anchor_table="anchors",
                candidate_table="candidates", candidate_cap=2,
            )
            with self.assertRaisesRegex(ValueError, "cap mismatch"):
                validate_candidate_cache(path, expected_cap=640)

    def test_unknown_target_is_rejected_on_import(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.csv.gz"
            c = self.make_db()
            self.make_candidates(c)
            export_candidate_cache(
                c, path, split="train", anchor_table="anchors",
                candidate_table="candidates", candidate_cap=2,
            )
            target = self.make_db(("s2_a", "s3_c"))
            with self.assertRaisesRegex(ValueError, "unknown/source-mismatched targets"):
                import_candidate_cache(
                    target, path, anchor_table="anchors", result_table="restored"
                )

    def test_export_rejects_unknown_anchor_without_silent_drop(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.csv.gz"
            c = self.make_db()
            self.make_candidates(c)
            rid = c.execute("SELECT rowid FROM train WHERE entity_id='s2_a'").fetchone()[0]
            c.execute("INSERT INTO candidates VALUES (?,?,?,?)", ("missing_anchor", rid, 1.0, 1))
            with self.assertRaisesRegex(ValueError, "unknown anchors"):
                export_candidate_cache(
                    c, path, split="train", anchor_table="anchors",
                    candidate_table="candidates", candidate_cap=3,
                )

    def test_unsafe_table_identifier_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.csv.gz"
            c = self.make_db()
            self.make_candidates(c)
            with self.assertRaisesRegex(ValueError, "Unsafe SQL identifier"):
                export_candidate_cache(
                    c, path, split="train;drop", anchor_table="anchors",
                    candidate_table="candidates", candidate_cap=2,
                )


if __name__ == "__main__":
    unittest.main()
