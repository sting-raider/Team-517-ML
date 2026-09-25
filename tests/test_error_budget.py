import unittest

from ber.error_budget import cap_conversion, decompose_slice


class ErrorBudgetTests(unittest.TestCase):
    def test_selected_confirmation_arithmetic(self):
        metrics = {
            "entities": 5000,
            "macro_f0_5": 0.928834953202575,
            "blocking_oracle_macro_f0_5": 0.9809513534570724,
            "singleton_count": 291,
            "singleton_false_positive_rate": 0.10652920962199312,
        }
        result = decompose_slice(metrics)
        self.assertAlmostEqual(result["retrieval_ceiling_gap"], 0.019048646542927594)
        self.assertAlmostEqual(result["within_candidate_model_decision_gap"], 0.052116400254497375)
        self.assertEqual(result["singleton_false_positive_count"], 31)
        self.assertAlmostEqual(result["oracle_singleton_only_gain"], 31/5000)
        self.assertAlmostEqual(result["minimum_oracle_gain_for_target"], 0.017048646542927592)

    def test_rejects_impossible_oracle(self):
        with self.assertRaises(ValueError):
            decompose_slice({
                "entities": 10,
                "macro_f0_5": .9,
                "blocking_oracle_macro_f0_5": .8,
                "singleton_count": 1,
                "singleton_false_positive_rate": 0.0,
            })

    def test_cap_conversion(self):
        wide = {
            "retrieval_80": {
                "macro_f0_5": .90,
                "blocking_oracle_macro_f0_5": .95,
                "singleton_false_positive_rate": .10,
                "candidate_pair_recall": .90,
            },
            "retrieval_640": {
                "macro_f0_5": .91,
                "blocking_oracle_macro_f0_5": .97,
                "singleton_false_positive_rate": .11,
                "candidate_pair_recall": .94,
            },
        }
        result = cap_conversion(wide)
        self.assertAlmostEqual(result["historical_realized_fraction_of_added_oracle_headroom"], .5)
        self.assertAlmostEqual(result["singleton_fpr_delta"], .01)


if __name__ == "__main__":
    unittest.main()
