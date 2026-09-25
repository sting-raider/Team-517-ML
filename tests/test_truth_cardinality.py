import unittest
from ber.truth_cardinality import best_case_f05, fold, match_counts


class TruthCardinalityTests(unittest.TestCase):
    def test_match_counts(self):
        self.assertEqual(match_counts(""), (0, 0, 0))
        self.assertEqual(match_counts("S2-a,S3-b,S3-c"), (1, 2, 3))

    def test_best_case_f05_penalizes_false_positive_more_than_one_miss_for_multi_match(self):
        self.assertEqual(best_case_f05(0, 0), 1.0)
        self.assertEqual(best_case_f05(0, 1), 0.0)
        self.assertAlmostEqual(best_case_f05(2, 1), 5/6)
        self.assertAlmostEqual(best_case_f05(2, 3), 5/7)
        self.assertGreater(best_case_f05(2, 1), best_case_f05(2, 3))

    def test_fold_is_deterministic_and_valid(self):
        self.assertEqual(fold("S1-123"), fold("S1-123"))
        self.assertIn(fold("S1-123"), {"fit", "early", "calibrate", "holdout"})


if __name__ == "__main__":
    unittest.main()
