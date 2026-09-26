import tempfile
import unittest
from pathlib import Path

from tools import source1_rare_number_census as mod


class Source1RareNumberCensusTest(unittest.TestCase):
    def test_country_field_df_and_record_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tiny.tsv"
            path.write_text(
                "entity_id\tbusiness_name\tbusiness_address\tcountry\n"
                "a\tCafe 7\t12 Main St\tUS\n"
                "b\tCafe 7\t13 Main St\tUS\n"
                "c\tShop 99\t12 Side Rd\tIndia\n"
                "d\tShop 99\t14 14 Side Rd\tIndia\n",
                encoding="utf-8",
            )
            result = mod.analyze(path, "tiny")

        us_addr = result["countries"]["US"]["fields"]["address"]
        india_name = result["countries"]["India"]["fields"]["name"]
        india_addr = result["countries"]["India"]["fields"]["address"]

        self.assertEqual(result["rows"], 4)
        self.assertEqual(us_addr["record_coverage_by_df_cutoff"]["1"]["count"], 2)
        self.assertEqual(india_name["best_record_df_quantiles"]["p50"], 2)
        self.assertEqual(india_addr["record_coverage_by_df_cutoff"]["1"]["count"], 2)
        self.assertEqual(india_addr["records_with_repeated_numeric_token"], 1)

    def test_numeric_runs_preserve_leading_zeros(self):
        self.assertEqual(mod.DIGITS.findall("Unit 007 / 12B"), ["007", "12"])


if __name__ == "__main__":
    unittest.main()
