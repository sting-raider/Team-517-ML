import unittest

from ber.uncertainty import (
    compare_slices,
    exact_sign_test,
    paired_bootstrap,
)


class PairedBootstrapTests(unittest.TestCase):
    def test_exact_tie(self):
        scores = {"a": 0.2, "b": 0.4, "c": 1.0}
        result = paired_bootstrap(scores, scores, iterations=200, seed=7)
        self.assertEqual(result["paired_mean_delta"], 0.0)
        self.assertEqual(result["bootstrap_delta_interval"], [0.0, 0.0])
        self.assertEqual(result["wins"], 0)
        self.assertEqual(result["losses"], 0)
        self.assertEqual(result["ties"], 3)
        self.assertEqual(result["exact_sign_test_p"], 1.0)

    def test_known_uniform_improvement(self):
        baseline = {"a": 0.0, "b": 0.0, "c": 0.0}
        candidate = {"a": 1.0, "b": 1.0, "c": 1.0}
        result = paired_bootstrap(
            baseline, candidate, iterations=200, seed=517
        )
        self.assertEqual(result["paired_mean_delta"], 1.0)
        self.assertEqual(result["bootstrap_delta_interval"], [1.0, 1.0])
        self.assertEqual(result["bootstrap_probability_delta_gt_0"], 1.0)
        self.assertEqual(result["exact_sign_test_p"], 0.25)

    def test_anchor_mismatch_fails_by_default(self):
        with self.assertRaisesRegex(ValueError, "anchor universe mismatch"):
            paired_bootstrap({"a": 0.0}, {"b": 1.0}, iterations=10)

    def test_intersection_is_explicit(self):
        result = paired_bootstrap(
            {"a": 0.0, "b": 0.5},
            {"b": 0.75, "c": 1.0},
            iterations=50,
            intersection=True,
        )
        self.assertEqual(result["entities"], 1)
        self.assertEqual(result["paired_mean_delta"], 0.25)

    def test_seed_is_deterministic(self):
        baseline = {"a": 0.1, "b": 0.5, "c": 0.7}
        candidate = {"a": 0.2, "b": 0.4, "c": 0.9}
        one = paired_bootstrap(baseline, candidate, iterations=500, seed=517)
        two = paired_bootstrap(baseline, candidate, iterations=500, seed=517)
        self.assertEqual(one, two)

    def test_country_and_cardinality_slices(self):
        baseline = {"a": 0.0, "b": 0.5, "c": 0.2, "d": 0.9}
        candidate = {"a": 0.2, "b": 0.5, "c": 0.1, "d": 1.0}
        metadata = {
            "a": {"country": "India", "cardinality": "0"},
            "b": {"country": "India", "cardinality": "2"},
            "c": {"country": "US", "cardinality": "2"},
            "d": {"country": "US", "cardinality": "2"},
        }
        result = compare_slices(
            baseline, candidate, metadata,
            ["country", "cardinality"], iterations=100, seed=3,
        )
        self.assertEqual(result["country"]["India"]["entities"], 2)
        self.assertEqual(result["country"]["US"]["entities"], 2)
        self.assertEqual(result["cardinality"]["0"]["entities"], 1)
        self.assertEqual(result["cardinality"]["2"]["entities"], 3)

    def test_exact_sign_test(self):
        self.assertEqual(exact_sign_test(0, 0), 1.0)
        self.assertEqual(exact_sign_test(1, 1), 1.0)
        self.assertEqual(exact_sign_test(3, 0), 0.25)


if __name__ == "__main__":
    unittest.main()
