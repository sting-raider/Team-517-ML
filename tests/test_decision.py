import math
import unittest

from ber.decision import choose_expected_f05_prefix, expected_f05_prefix_utilities


def brute_force_prefix_utilities(probabilities):
    ordered = sorted(enumerate(probabilities), key=lambda item: (-item[1], item[0]))
    probs = [p for _, p in ordered]
    n = len(probs)
    utilities = [0.0] * (n + 1)

    for mask in range(1 << n):
        mass = 1.0
        truth_size = 0
        for i, p in enumerate(probs):
            if mask & (1 << i):
                mass *= p
                truth_size += 1
            else:
                mass *= 1.0 - p

        for k in range(n + 1):
            if truth_size == 0:
                score = float(k == 0)
            else:
                true_selected = sum(bool(mask & (1 << i)) for i in range(k))
                score = 1.25 * true_selected / (0.25 * truth_size + k)
            utilities[k] += mass * score

    return tuple(index for index, _ in ordered), tuple(utilities)


class ExpectedF05Tests(unittest.TestCase):
    def test_exact_dp_matches_exhaustive_truth_enumeration(self):
        cases = (
            (),
            (0.6,),
            (1.0, 0.0),
            (0.6, 0.4),
            (0.9, 0.55, 0.3),
            (0.4, 0.3, 0.1),
            (0.5, 0.4, 0.1),
            (0.51, 0.49, 0.49),
        )
        for probabilities in cases:
            with self.subTest(probabilities=probabilities):
                expected_order, expected = brute_force_prefix_utilities(probabilities)
                order, actual = expected_f05_prefix_utilities(probabilities)
                self.assertEqual(order, expected_order)
                self.assertEqual(len(actual), len(expected))
                for left, right in zip(actual, expected):
                    self.assertAlmostEqual(left, right, places=14)

    def test_empty_prediction_can_beat_every_nonempty_prefix(self):
        decision = choose_expected_f05_prefix([0.4, 0.3, 0.1])
        self.assertEqual(decision.prefix_size, 0)
        self.assertEqual(decision.selected_indices, ())
        self.assertAlmostEqual(decision.expected_f0_5, 0.378, places=14)
        self.assertAlmostEqual(decision.prefix_utilities[1], 0.3739047619047619, places=14)

    def test_multi_match_prefix_can_beat_top_one(self):
        decision = choose_expected_f05_prefix([0.5, 0.4, 0.1])
        self.assertEqual(decision.prefix_size, 2)
        self.assertEqual(decision.selected_indices, (0, 1))
        self.assertAlmostEqual(decision.expected_f0_5, 0.47318181818181826, places=14)

    def test_original_indices_are_returned_after_probability_sort(self):
        decision = choose_expected_f05_prefix([0.0, 1.0, 0.0])
        self.assertEqual(decision.sorted_indices, (1, 0, 2))
        self.assertEqual(decision.selected_indices, (1,))
        self.assertEqual(decision.prefix_size, 1)
        self.assertAlmostEqual(decision.expected_f0_5, 1.0)

    def test_empty_candidate_list_scores_one(self):
        decision = choose_expected_f05_prefix([])
        self.assertEqual(decision.selected_indices, ())
        self.assertEqual(decision.prefix_utilities, (1.0,))
        self.assertEqual(decision.expected_f0_5, 1.0)

    def test_probability_validation_and_explicit_size_bound(self):
        for bad in (-0.01, 1.01, math.nan, math.inf):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    choose_expected_f05_prefix([bad])
        with self.assertRaisesRegex(ValueError, "silently truncating"):
            choose_expected_f05_prefix([0.9, 0.8, 0.7], max_candidates=2)
        with self.assertRaises(ValueError):
            choose_expected_f05_prefix([0.5], tie_tolerance=-1.0)


if __name__ == "__main__":
    unittest.main()
