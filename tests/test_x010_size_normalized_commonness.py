import math
import unittest
from collections import Counter

from tools.experiments.x010_size_normalized_commonness import (
    norm_proxy,
    raw_frequency_hist,
    transform_hist,
    transform_value,
    weighted_ks,
)


class X010CommonnessTests(unittest.TestCase):
    def test_normalizer_matches_v2_semantics_examples(self):
        self.assertEqual(norm_proxy("  Café--12/A  "), "cafe 12 a")
        self.assertEqual(norm_proxy("Müller & Söhne"), "muller sohne")
        self.assertEqual(norm_proxy("SHOP # 007"), "shop 007")
        self.assertEqual(norm_proxy(""), "")

    def test_transform_formulas_and_empty_handling(self):
        self.assertEqual(transform_value(0, 1_000_000, "raw_log1p"), 0.0)
        self.assertEqual(transform_value(0, 1_000_000, "per_million_log1p"), 0.0)
        self.assertEqual(transform_value(0, 1_000_000, "self_information"), 0.0)
        self.assertAlmostEqual(transform_value(1, 1_000_000, "raw_log1p"), math.log(2))
        self.assertAlmostEqual(transform_value(1, 1_000_000, "per_million_log1p"), math.log(2))
        self.assertAlmostEqual(
            transform_value(1, 1_000_000, "self_information"),
            math.log(1_000_001 / 2),
        )

    def test_row_weighted_frequency_hist(self):
        counter = Counter({"unique": 1, "duplicate": 2, "": 3})
        self.assertEqual(raw_frequency_hist(counter), Counter({0: 3, 2: 2, 1: 1}))
        transformed = transform_hist(raw_frequency_hist(counter), 6, "raw_log1p")
        self.assertEqual(sum(transformed.values()), 6)

    def test_weighted_ks(self):
        left = Counter({0.0: 2, 1.0: 2})
        self.assertEqual(weighted_ks(left, left), 0.0)
        right = Counter({0.0: 4})
        self.assertAlmostEqual(weighted_ks(left, right), 0.5)


if __name__ == "__main__":
    unittest.main()
