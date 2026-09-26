import importlib.util
import unittest
from collections import Counter
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "experiments" / "x009_int002_frequency_shift.py"
SPEC = importlib.util.spec_from_file_location("x009", MODULE)
x009 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(x009)


class X009FrequencyShiftTests(unittest.TestCase):
    def test_normalizer_matches_expected_fold(self):
        self.assertEqual(x009.norm_proxy("  Café--12/A  "), "cafe 12 a")
        self.assertEqual(x009.norm_proxy("Müller & Söhne"), "muller sohne")
        self.assertEqual(x009.norm_proxy("SHOP # 007"), "shop 007")

    def test_frequency_hist_matches_v2_empty_semantics(self):
        self.assertEqual(
            x009.freq_hist(Counter({"x": 3, "y": 1, "": 2})),
            Counter({3: 3, 0: 2, 1: 1}),
        )

    def test_weighted_quantile(self):
        self.assertEqual(x009.weighted_quantile(Counter({1: 9, 10: 1}), 0.5), 1.0)
        self.assertEqual(x009.weighted_quantile(Counter({1: 9, 10: 1}), 1.0), 10.0)

    def test_weighted_ks(self):
        self.assertEqual(x009.weighted_ks({1: 10}, {1: 10}), 0.0)
        self.assertAlmostEqual(x009.weighted_ks({1: 10}, {2: 10}), 1.0)

    def test_fold517_known_values(self):
        self.assertEqual(x009.fold517("S1_000000001"), "fit")
        self.assertEqual(x009.fold517("S1_000000002"), "calibrate")
        self.assertEqual(x009.fold517("S1_000000003"), "early")
        self.assertEqual(x009.fold517("S1_000000004"), "fit")


if __name__ == "__main__":
    unittest.main()
