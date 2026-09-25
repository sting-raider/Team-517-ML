import unittest

import numpy as np

from ber.s1_cardinality_prior import (
    _auc,
    _average_precision,
    fold_name,
    normalize,
    targeting_metrics,
    truth_cardinality,
)


class Source1CardinalityPriorTests(unittest.TestCase):
    def test_truth_cardinality(self):
        self.assertEqual(truth_cardinality(""), 0)
        self.assertEqual(truth_cardinality("S2-a"), 1)
        self.assertEqual(truth_cardinality("S2-a, S3-b,S3-c"), 3)

    def test_fold_is_deterministic(self):
        self.assertEqual(fold_name("S1-123"), fold_name("S1-123"))
        self.assertIn(fold_name("S1-123"), {"fit", "early", "calibrate", "holdout"})

    def test_normalize(self):
        self.assertEqual(normalize("Café, 12-B!"), "cafe 12 b")
        self.assertEqual(normalize("  ACME   ROAD  "), "acme road")

    def test_binary_rank_metrics(self):
        y = np.array([0, 0, 1, 1], dtype=np.uint8)
        perfect = np.array([0.1, 0.2, 0.8, 0.9])
        self.assertAlmostEqual(_auc(y, perfect), 1.0)
        self.assertAlmostEqual(_average_precision(y, perfect), 1.0)
        tied = np.ones(4)
        self.assertAlmostEqual(_auc(y, tied), 0.5)
        self.assertAlmostEqual(_average_precision(y, tied), 0.5)

    def test_targeting_random_shape(self):
        y = np.array([1, 0, 1, 0], dtype=np.uint8)
        score = np.array([.9, .8, .7, .6])
        out = targeting_metrics(y, score, fractions=(.5,))
        self.assertEqual(out["0.5"]["selected"], 2)
        self.assertAlmostEqual(out["0.5"]["precision"], .5)
        self.assertAlmostEqual(out["0.5"]["recall"], .5)


if __name__ == "__main__":
    unittest.main()
