import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools" / "experiments" / "i036_int006_error_budget.py"
spec = importlib.util.spec_from_file_location("i036", MODULE)
i036 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i036)


class ErrorBudgetTest(unittest.TestCase):
    def test_decomposition_is_additive(self):
        result = i036.decompose(0.90, 0.97, 0.998)
        self.assertAlmostEqual(result["total_deficit"], 0.10)
        self.assertAlmostEqual(result["retrieval_ceiling_loss"], 0.03)
        self.assertAlmostEqual(result["within_candidate_loss"], 0.07)
        self.assertAlmostEqual(
            result["retrieval_share_of_deficit"] + result["within_candidate_share_of_deficit"],
            1.0,
        )

    def test_transition_components_sum_to_score_gain(self):
        result = i036.transition(0.90, 0.96, 0.94, 0.98)
        self.assertAlmostEqual(
            result["score_gain"],
            result["oracle_gain"] + result["within_candidate_gap_reduction"],
        )

    def test_invalid_score_above_oracle_fails(self):
        with self.assertRaises(ValueError):
            i036.decompose(0.98, 0.97)

    def test_current_neural32_numbers(self):
        result = i036.decompose(0.9707021141747368, 0.9928230369823905)
        self.assertAlmostEqual(result["retrieval_ceiling_loss"], 0.007176963017609506)
        self.assertGreater(result["within_candidate_share_of_deficit"], 0.75)
        self.assertAlmostEqual(
            result["fraction_of_current_retrieval_loss_to_remove_for_target_oracle"],
            0.7213305969261968,
        )


if __name__ == "__main__":
    unittest.main()
