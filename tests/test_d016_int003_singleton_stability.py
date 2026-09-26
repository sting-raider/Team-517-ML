import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "experiments" / "d016_int003_singleton_stability.py"
SPEC = importlib.util.spec_from_file_location("d016", MODULE)
d016 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d016)


class D016Tests(unittest.TestCase):
    def test_exact_fp_count(self):
        self.assertEqual(d016.exact_fp_count(114, 8 / 114), 8)
        with self.assertRaises(ValueError):
            d016.exact_fp_count(10, 0.155)

    def test_wilson_contains_observed_rate(self):
        lo, hi = d016.wilson_interval(13, 262)
        self.assertLess(lo, 13 / 262)
        self.assertGreater(hi, 13 / 262)

    def test_extract_headroom(self):
        row = {
            "entities": 5000,
            "singleton_count": 262,
            "singleton_false_positive_rate": 13 / 262,
            "macro_f0_5": 0.95,
            "blocking_oracle_macro_f0_5": 0.98,
        }
        got = d016.extract_metric(row)
        self.assertEqual(got["false_positives"], 13)
        self.assertAlmostEqual(got["perfect_singleton_fix_macro_headroom"], 13 / 5000)

    def test_pooled_descriptive(self):
        rows = {
            "calibrate": {"all": {"false_positives": 16, "singleton_count": 252, "false_positive_rate": 16/252}},
            "holdout": {"all": {"false_positives": 21, "singleton_count": 199, "false_positive_rate": 21/199}},
            "confirmation": {"all": {"false_positives": 13, "singleton_count": 262, "false_positive_rate": 13/262}},
        }
        got = d016.pooled_descriptive(rows, "all")
        self.assertEqual(got["false_positives"], 50)
        self.assertEqual(got["singleton_count"], 713)
        self.assertAlmostEqual(got["false_positive_rate"], 50/713)


if __name__ == "__main__":
    unittest.main()
