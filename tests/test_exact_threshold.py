import unittest

import numpy as np

from ber.thresholds import choose_threshold_exact


def row_score(truth, predicted):
    truth, predicted = set(truth), set(predicted)
    if not truth:
        return float(not predicted)
    return 1.25 * len(truth & predicted) / (0.25 * len(truth) + len(predicted))


def brute_score(meta, groups, target, prob, indices, threshold):
    pred = {i: [] for i in indices}
    for g, t, p in zip(groups, target, prob):
        if g in pred and p >= threshold:
            pred[g].append(t)
    return sum(row_score(meta[i]["truth"], pred[i]) for i in indices) / len(indices)


def coarse_grid_best(meta, groups, target, prob, indices):
    grid = np.unique(np.r_[np.arange(.05, .96, .025), .97, .98, .99, .995, .999])
    scored = [(brute_score(meta, groups, target, prob, indices, float(t)), float(t)) for t in grid]
    score, threshold = max(scored, key=lambda x: (x[0], x[1]))
    return threshold, score


class ExactThresholdTests(unittest.TestCase):
    def test_finds_breakpoint_missed_by_coarse_grid(self):
        meta = [{"truth": {"true"}}]
        groups = np.array([0, 0])
        target = np.array(["true", "false"])
        prob = np.array([0.613, 0.612])

        exact_t, exact = choose_threshold_exact(meta, groups, target, prob, [0])
        grid_t, grid_score = coarse_grid_best(meta, groups, target, prob, [0])

        self.assertEqual(exact_t, 0.613)
        self.assertEqual(exact["macro_f0_5"], 1.0)
        self.assertLess(grid_score, exact["macro_f0_5"])
        self.assertNotEqual(grid_t, exact_t)

    def test_exact_weakly_dominates_grid_on_mixed_small_case(self):
        meta = [
            {"truth": set()},
            {"truth": {"a", "b"}},
            {"truth": {"c"}},
        ]
        groups = np.array([0, 1, 1, 1, 2, 2])
        target = np.array(["x", "a", "b", "z", "c", "q"])
        prob = np.array([0.91, 0.77, 0.63, 0.61, 0.58, 0.20])

        exact_t, exact = choose_threshold_exact(meta, groups, target, prob, range(3))
        _, grid_score = coarse_grid_best(meta, groups, target, prob, range(3))

        self.assertGreaterEqual(exact["macro_f0_5"], grid_score)
        self.assertAlmostEqual(
            exact["macro_f0_5"],
            brute_score(meta, groups, target, prob, range(3), exact_t),
        )

    def test_duplicate_probabilities_enter_together(self):
        meta = [{"truth": {"a"}}]
        groups = np.array([0, 0])
        target = np.array(["a", "false"])
        prob = np.array([0.7, 0.7])

        threshold, result = choose_threshold_exact(meta, groups, target, prob, [0])

        self.assertEqual(threshold, 0.7)
        self.assertAlmostEqual(result["macro_f0_5"], 1.25 / 2.25)

    def test_candidate_miss_stays_in_truth_denominator(self):
        meta = [{"truth": {"a", "missing"}}]
        groups = np.array([0])
        target = np.array(["a"])
        prob = np.array([0.7])

        threshold, result = choose_threshold_exact(meta, groups, target, prob, [0])

        self.assertEqual(threshold, 0.7)
        self.assertAlmostEqual(result["macro_f0_5"], 1.25 / 1.5)

    def test_singleton_empty_set_tie_prefers_higher_threshold(self):
        meta = [{"truth": set()}, {"truth": {"a"}}]
        groups = np.array([0, 1])
        target = np.array(["x", "a"])
        prob = np.array([0.9, 0.8])

        threshold, result = choose_threshold_exact(meta, groups, target, prob, [0, 1])

        self.assertEqual(threshold, 1.0)
        self.assertAlmostEqual(result["macro_f0_5"], 0.5)

    def test_no_candidates_returns_all_empty_score(self):
        meta = [{"truth": set()}, {"truth": {"a"}}]
        threshold, result = choose_threshold_exact(
            meta,
            np.array([], dtype=int),
            np.array([], dtype=str),
            np.array([], dtype=float),
            [0, 1],
        )
        self.assertEqual(threshold, 1.0)
        self.assertAlmostEqual(result["macro_f0_5"], 0.5)

    def test_rejects_nonfinite_or_out_of_range_probabilities(self):
        meta = [{"truth": {"a"}}]
        with self.assertRaises(ValueError):
            choose_threshold_exact(meta, [0], ["a"], [float("nan")], [0])
        with self.assertRaises(ValueError):
            choose_threshold_exact(meta, [0], ["a"], [1.01], [0])


if __name__ == "__main__":
    unittest.main()
