import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).parents[1] / "tools" / "experiments" / "r030_char_cardinality_prior.py"
spec = importlib.util.spec_from_file_location("r030", MODULE_PATH)
r030 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r030)


class R030CharCardinalityPriorTests(unittest.TestCase):
    def test_truth_cardinality(self):
        self.assertEqual(r030.truth_cardinality(""), 0)
        self.assertEqual(r030.truth_cardinality("S2-a"), 1)
        self.assertEqual(r030.truth_cardinality("S2-a,S3-b,S3-c"), 3)

    def test_fold_bucket_is_deterministic(self):
        bucket = r030.fold_bucket("S1-123")
        self.assertEqual(bucket, r030.fold_bucket("S1-123"))
        self.assertTrue(0 <= bucket < 100)

    def test_normalize_name_series(self):
        values = pd.Series([" Café__du  Monde!! ", "ACME   ROAD"])
        self.assertEqual(
            r030.normalize_name_series(values).tolist(),
            ["café du monde", "acme road"],
        )

    def test_targeting_perfect_ranking(self):
        y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.uint8)
        score = np.array([1, .9, .8, .7, .6, .5, .4, .3, .2, .1])
        result = r030.targeting_metrics(y, score, fractions=(.2,))["0.2"]
        self.assertAlmostEqual(result["recall"], 1.0)
        self.assertAlmostEqual(result["precision"], 1.0)
        self.assertAlmostEqual(result["lift"], 5.0)

    def test_binary_metrics_perfect(self):
        y = np.array([0, 0, 1, 1], dtype=np.uint8)
        probability = np.array([.1, .2, .8, .9])
        result = r030.binary_metrics(y, probability, probability)
        self.assertAlmostEqual(result["auroc"], 1.0)
        self.assertAlmostEqual(result["auprc"], 1.0)


if __name__ == "__main__":
    unittest.main()
