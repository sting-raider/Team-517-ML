import inspect
import tempfile
import unittest
from pathlib import Path

from ber.blocking import build_index, candidates
from ber.data import connect
from ber.features import FEATURE_NAMES, features


class LeakageGuardTests(unittest.TestCase):
    def test_feature_schema_excludes_identifiers_and_labels(self):
        self.assertEqual(
            tuple(inspect.signature(features).parameters),
            ("n1", "a1", "n2", "a2", "retrieval", "hits", "source"),
        )
        forbidden = {"entity_id", "country", "truth", "label", "target", "target_id"}
        self.assertTrue(forbidden.isdisjoint(FEATURE_NAMES))
        self.assertEqual(len(FEATURE_NAMES), 47)

    def test_truth_does_not_inject_unretrievable_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = connect(Path(tmp) / "audit.duckdb")
            c.execute("""CREATE TABLE train(
                entity_id VARCHAR,
                business_name VARCHAR,
                business_address VARCHAR,
                country VARCHAR,
                source INTEGER,
                n VARCHAR,
                a VARCHAR
            )""")
            c.executemany(
                "INSERT INTO train VALUES (?,?,?,?,?,?,?)",
                [
                    ("S1-A", "Alpha", "1 Oak", "US", 1, "alpha", "1 oak"),
                    ("S2-NEG", "Alpha", "1 Oak", "US", 2, "alpha", "1 oak"),
                    ("S2-POS", "Zulu", "999 Nowhere", "US", 2, "zulu", "999 nowhere"),
                ],
            )
            c.execute("CREATE TABLE truth(anchor VARCHAR, matches VARCHAR)")
            c.execute("INSERT INTO truth VALUES ('S1-A', 'S2-POS')")
            build_index(c, "train")
            c.execute("CREATE TABLE anchors AS SELECT * FROM train WHERE source=1")
            candidates(c, "train", "anchors", "audit_candidates", cap=80)
            retrieved = {
                row[0]
                for row in c.execute(
                    """SELECT r.entity_id
                       FROM audit_candidates p
                       JOIN train r ON p.rid=r.rowid
                       WHERE p.anchor='S1-A'"""
                ).fetchall()
            }
            c.close()

            self.assertIn("S2-NEG", retrieved)
            self.assertNotIn(
                "S2-POS",
                retrieved,
                "Ground-truth membership must not cause an otherwise unretrievable pair to enter candidates",
            )


if __name__ == "__main__":
    unittest.main()
