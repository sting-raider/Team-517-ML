import itertools
import unittest

from ber.metrics import evaluate, row_score


def count_formula(truth, predicted):
    truth = set(truth)
    predicted = set(predicted)
    if not truth:
        return float(not predicted)
    tp = len(truth & predicted)
    fp = len(predicted - truth)
    fn = len(truth - predicted)
    return 1.25 * tp / (1.25 * tp + fp + 0.25 * fn)


def precision_recall_formula(truth, predicted):
    truth = set(truth)
    predicted = set(predicted)
    if not truth:
        return float(not predicted)
    if not predicted:
        return 0.0
    tp = len(truth & predicted)
    precision = tp / len(predicted)
    recall = tp / len(truth)
    denominator = 0.25 * precision + recall
    return 1.25 * precision * recall / denominator if denominator else 0.0


class MetricParityTests(unittest.TestCase):
    def test_exhaustive_small_set_parity(self):
        universe = ("a", "b", "c", "d")
        for truth_size in range(len(universe) + 1):
            for truth in itertools.combinations(universe, truth_size):
                for predicted_size in range(len(universe) + 1):
                    for predicted in itertools.combinations(universe, predicted_size):
                        actual = row_score(truth, predicted)
                        self.assertAlmostEqual(actual, count_formula(truth, predicted), places=15)
                        self.assertAlmostEqual(
                            actual, precision_recall_formula(truth, predicted), places=15
                        )

    def test_set_semantics_are_explicit(self):
        self.assertEqual(row_score(["x"], ["x", "x"]), 1.0)
        self.assertEqual(row_score(["x", "x"], ["x"]), 1.0)

    def test_macro_is_entity_weighted_not_pair_weighted(self):
        truth = {"singleton": [], "large": [f"x{i}" for i in range(100)]}
        predicted = {"singleton": [], "large": []}
        report = evaluate(truth, predicted)
        self.assertEqual(report["macro_f0_5"], 0.5)

    def test_retrieval_diagnostics_have_distinct_denominators(self):
        truth = {
            "a": {"x1", "x2"},
            "b": {"y1"},
            "c": set(),
            "d": {"z1", "z2", "z3"},
        }
        candidates = {
            "a": {"x1", "junk"},
            "b": set(),
            "c": {"junk-singleton"},
            "d": {"z1", "z2"},
        }
        report = evaluate(truth, {}, candidates)
        self.assertAlmostEqual(report["candidate_pair_recall"], 3 / 6)
        self.assertAlmostEqual(
            report["candidate_entity_recall"], (1 / 2 + 0 + 2 / 3) / 3
        )
        self.assertAlmostEqual(report["all_matches_retrieved_rate"], 0.0)
        expected_oracle = (
            row_score(truth["a"], {"x1"})
            + row_score(truth["b"], set())
            + 1.0
            + row_score(truth["d"], {"z1", "z2"})
        ) / 4
        self.assertAlmostEqual(report["blocking_oracle_macro_f0_5"], expected_oracle)

        any_match_entity_recall = (1 + 0 + 1) / 3
        self.assertNotAlmostEqual(
            report["candidate_entity_recall"], any_match_entity_recall
        )

    def test_retrieval_oracle_ignores_false_candidates(self):
        truth = {"singleton": set(), "positive": {"x"}}
        candidates = {
            "singleton": {"bad1", "bad2"},
            "positive": {"x", "bad3"},
        }
        report = evaluate(truth, {}, candidates)
        self.assertEqual(report["blocking_oracle_macro_f0_5"], 1.0)
        self.assertEqual(report["candidate_pair_recall"], 1.0)
        self.assertEqual(report["all_matches_retrieved_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
