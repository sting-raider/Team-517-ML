import csv
import tempfile
import unittest
from pathlib import Path

from ber import token_idf_audit as m


class TestTokenIdfAudit(unittest.TestCase):
    def test_country_partition_and_probe_limit(self):
        rows = [
            ["a", "Alpha Beta Gamma Delta Epsilon", "10 Main Road North South West", "US"],
            ["b", "Alpha Beta", "20 Main Road North", "US"],
            ["c", "Alpha", "30 Main Road", "US"],
            ["d", "Alpha Beta Gamma Delta Epsilon", "12 MG Road Sector Five Block East", "India"],
            ["e", "Zeta", "No 7 Sector Five Block West", "India"],
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s1.tsv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter="\t")
                w.writerow(["entity_id", "business_name", "business_address", "country"])
                w.writerows(rows)
            out = m.audit(p, max_probes=2)
        self.assertEqual(out["countries"]["US"]["meta"]["records"], 3)
        self.assertEqual(out["countries"]["India"]["meta"]["records"], 2)
        self.assertEqual(out["countries"]["US"]["name"]["vocab"], 5)
        self.assertEqual(out["countries"]["India"]["name"]["vocab"], 6)
        self.assertNotIn("road", m.address_words("10 Main Road North"))
        self.assertNotIn("10", m.address_words("10 Main Road North"))
        self.assertGreater(out["countries"]["US"]["name"]["dropped_by_probe_limit"], 0)
        self.assertEqual(
            out["countries"]["US"]["meta"]["digit_address_coverage_rate"], 1.0
        )

    def test_normalization(self):
        self.assertEqual(m.normalize("  Café--NO. 12  "), "cafe no 12")


if __name__ == "__main__":
    unittest.main()
