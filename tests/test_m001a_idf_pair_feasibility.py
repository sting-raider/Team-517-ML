import math
import unittest

from tools.experiments.m001a_idf_pair_feasibility import (
    idf_weight,
    normalize,
    token_set,
    weighted_overlap,
)


class TestM001aIdfPairFeasibility(unittest.TestCase):
    def test_normalize_and_tokens(self):
        self.assertEqual(normalize("  Café--NO. 12  "), "cafe no 12")
        self.assertEqual(token_set("Café, Café 12"), {"cafe", "12"})

    def test_exact_and_empty_semantics(self):
        w = {"alpha": 2.0, "beta": 5.0}
        self.assertEqual(
            weighted_overlap({"alpha", "beta"}, {"alpha", "beta"}, w),
            (1.0, 1.0, 1.0, 1.0),
        )
        self.assertEqual(weighted_overlap(set(), set(), {}), (0.0, 0.0, 0.0, 0.0))

    def test_rare_token_loss_is_penalized_more(self):
        weights = {"rare": 5.0, "common": 1.0, "shared": 2.0}
        original = {"rare", "common", "shared"}
        rare_deleted = {"common", "shared"}
        common_deleted = {"rare", "shared"}
        self.assertLess(
            weighted_overlap(original, rare_deleted, weights)[0],
            weighted_overlap(original, common_deleted, weights)[0],
        )

    def test_uniform_weight_scaling_invariance_and_bounds(self):
        left, right = {"a", "b"}, {"b", "c"}
        x = weighted_overlap(left, right, {"a": 2, "b": 3, "c": 4})
        y = weighted_overlap(left, right, {"a": 20, "b": 30, "c": 40})
        for a, b in zip(x, y):
            self.assertAlmostEqual(a, b, places=12)
            self.assertGreaterEqual(a, 0.0)
            self.assertLessEqual(a, 1.0)

    def test_idf_is_positive_and_monotone(self):
        rare = idf_weight(1000, 1)
        common = idf_weight(1000, 900)
        self.assertGreater(rare, common)
        self.assertGreater(common, 0.0)
        with self.assertRaises(ValueError):
            idf_weight(10, 11)


if __name__ == "__main__":
    unittest.main()
