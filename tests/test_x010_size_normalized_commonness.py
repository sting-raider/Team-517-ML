import importlib.util
import math
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "experiments" / "x010_size_normalized_commonness.py"
SPEC = importlib.util.spec_from_file_location("x010", MODULE)
x010 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(x010)


class X010CommonnessTests(unittest.TestCase):
    def test_normalizer_semantics(self):
        self.assertEqual(x010.norm_proxy("  Café--12/A  "), "cafe 12 a")
        self.assertEqual(x010.norm_proxy("Mülller & Söhne".replace("lll", "ll")), "muller sohne")
        self.assertEqual(x010.norm_proxy("SHOP # 007"), "shop 007")

    def test_transform_empty_stays_zero(self):
        for kind in x010.TRANSFORMS:
            self.assertEqual(x010.transform_value(0, 1000, kind), 0.0)

    def test_raw_log1p(self):
        self.assertAlmostEqual(
            x010.transform_value(14, 1000, "raw_log1p"), math.log(15)
        )

    def test_per_million_depends_on_country_rows(self):
        small = x010.transform_value(1, 500_000, "per_million")
        large = x010.transform_value(1, 1_000_000, "per_million")
        self.assertGreater(small, large)

    def test_self_information_depends_on_country_rows(self):
        small = x010.transform_value(1, 500_000, "self_information")
        large = x010.transform_value(1, 1_000_000, "self_information")
        self.assertLess(small, large)

    def test_weighted_ks_identity_and_separation(self):
        self.assertEqual(x010.weighted_ks({1.0: 10}, {1.0: 20}), 0.0)
        self.assertEqual(x010.weighted_ks({1.0: 10}, {2.0: 10}), 1.0)

    def test_oos_counts_both_sides(self):
        out = x010.outside_fit_range(
            {0.0: 2, 1.0: 5, 3.0: 3}, {1.0: 4, 2.0: 6}
        )
        self.assertEqual(out["below_fit_min_rows"], 2)
        self.assertEqual(out["above_fit_max_rows"], 3)
        self.assertEqual(out["outside_fit_range_rows"], 5)


if __name__ == "__main__":
    unittest.main()
