import csv
import tempfile
import unittest
from pathlib import Path

from ber.address_collision_audit import audit_source1, normalize_repo_like


class AddressCollisionAuditTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_repo_like(" Café--12/B "), "cafe 12 b")
        self.assertEqual(normalize_repo_like("MÜNCHEN"), "munchen")
        self.assertEqual(normalize_repo_like("  A___B  "), "a b")

    def test_synthetic_collision_metrics(self):
        rows = [
            ["entity_id", "business_name", "business_address", "country"],
            ["S1_1", "Alpha Mart", "12 Main St.", "US"],
            ["S1_2", "Beta Foods", "12 Main St", "US"],
            ["S1_3", "Alpha Mart", "12 Main St", "US"],
            ["S1_4", "Unique", "88 Elsewhere", "US"],
            ["S1_5", "Alpha India", "9 Long Road", "India"],
            ["S1_6", "Alpha Cafe", "9 Long Road", "India"],
        ]
        with tempfile.TemporaryDirectory() as td:
            input_path = Path(td) / "source1.tsv"
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle, delimiter="\t", lineterminator="\n").writerows(rows)
            result = audit_source1(input_path, Path(td) / "work", chunk_rows=2)

        us = result["US"]
        self.assertEqual(us["records"], 4)
        self.assertEqual(us["collision_groups"], 1)
        self.assertEqual(us["collision_records"], 3)
        self.assertEqual(us["collision_pairs"], 3)
        self.assertEqual(us["same_name_pairs_within_collisions"], 1)
        self.assertEqual(us["cross_name_pairs"], 2)
        self.assertEqual(us["hard_negative_like_groups"], 1)

        india = result["India"]
        self.assertEqual(india["collision_groups"], 1)
        self.assertEqual(india["cross_name_pairs"], 1)
        self.assertEqual(result["ALL"]["records"], 6)
        self.assertFalse(result["protocol"]["entity_id_used_as_evidence"])


if __name__ == "__main__":
    unittest.main()
