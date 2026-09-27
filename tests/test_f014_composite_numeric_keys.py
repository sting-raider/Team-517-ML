import csv
import tempfile
import unittest
from pathlib import Path

from tools.experiments.f014_composite_numeric_keys import analyze_country, evidence, norm


class F014CompositeNumericKeysTest(unittest.TestCase):
    def test_normalization_and_dedup_semantics(self):
        self.assertEqual(norm("Café—12/A"), "cafe 12 a")
        number, name_words, address_words = evidence(
            "Alpha Alpha Store", "12 Market Market Road"
        )
        self.assertEqual(number, "12")
        self.assertEqual(name_words, {"alpha", "store"})
        self.assertEqual(address_words, {"market"})

    def test_composites_rescue_common_number(self):
        rows = [
            ("1", "Alpha Store", "12 Market Road", "India"),
            ("2", "Beta Market", "12 Market Road", "India"),
            ("3", "Alpha Cafe", "12 Lake View", "India"),
            ("4", "Gamma Shop", "99 Hill Lane", "India"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s1.tsv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["entity_id", "business_name", "business_address", "country"])
                writer.writerows(rows)

            result = analyze_country(path, "India")

        self.assertEqual(result["rows"], 4)
        self.assertEqual(result["families"]["number"]["coverage"]["1"], 0.25)
        self.assertEqual(result["families"]["number_address"]["coverage"]["1"], 0.50)
        self.assertEqual(result["families"]["number_name"]["coverage"]["1"], 1.0)
        self.assertEqual(
            result["rescue_over_number_only"]["number_address"]["1"]["rows"], 1
        )
        self.assertEqual(
            result["rescue_over_number_only"]["number_name"]["1"]["rows"], 3
        )


if __name__ == "__main__":
    unittest.main()
