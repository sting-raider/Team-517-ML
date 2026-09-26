import math
import unittest
from collections import Counter

from tools.experiments.m001b_idf_transfer_audit import (
    average_ranks,
    compare_profiles,
    spearman,
    weighted_quantiles,
)


class TestM001bIdfTransferAudit(unittest.TestCase):
    def test_weighted_quantiles(self):
        got = weighted_quantiles([1, 2, 3], [1, 8, 1], (.5, .9))
        self.assertEqual(got["0.5"], 2.0)
        self.assertEqual(got["0.9"], 2.0)

    def test_average_ranks_with_ties(self):
        self.assertEqual(average_ranks([5, 1, 1, 9]).tolist(), [2.0, .5, .5, 3.0])

    def test_spearman_perfect_and_reverse(self):
        self.assertAlmostEqual(spearman([1, 2, 3], [10, 20, 30]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3], [30, 20, 10]), -1.0)

    def test_compare_profiles_reports_novel_mass_and_stability(self):
        train = {
            "rows": 100,
            "name": Counter({"a": 10, "b": 20}),
            "address": Counter(),
        }
        test = {
            "rows": 50,
            "name": Counter({"a": 5, "b": 10, "c": 1}),
            "address": Counter(),
        }
        got = compare_profiles(train, test, "name")
        self.assertEqual(got["shared_vocab"], 2)
        self.assertAlmostEqual(got["test_posting_unseen_rate"], 1 / 16)
        self.assertAlmostEqual(got["shared_df_spearman"], 1.0)
        self.assertLess(got["shared_test_posting_weighted_abs_idf_drift_mean"], .02)


if __name__ == "__main__":
    unittest.main()
