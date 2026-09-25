import csv
import json
import tempfile
import unittest
from pathlib import Path

from ber.france_audit import nfkd_fold, scan_source1


class FranceAuditTests(unittest.TestCase):
    def test_nfkd_fold_and_aggregate_only_scan(self):
        self.assertEqual(nfkd_fold("École"), "Ecole")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source1.tsv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["entity_id", "business_name", "business_address", "country"])
                writer.writerow(["S1-1", "Café Bleu", "10 rue de l'École", "France"])
                writer.writerow(["S1-2", "Alpha LLC", "12 Road", "US"])
            result = scan_source1(path, france_details=True)
        france = result["countries"]["France"]
        self.assertEqual(france["records"], 1)
        self.assertEqual(france["name"]["nonascii_pct"], 100.0)
        self.assertEqual(france["address"]["nfkd_fold_changed_pct"], 100.0)
        self.assertEqual(
            result["france_details"]["top_name_tokens_nfkd_folded"][0],
            ("cafe", 1),
        )
        serialized = json.dumps(result)
        self.assertNotIn("S1-1", serialized)
        self.assertNotIn("Café Bleu", serialized)


if __name__ == "__main__":
    unittest.main()
