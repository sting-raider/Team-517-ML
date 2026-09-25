import unittest

from ber.uncertainty import (
    BOOTSTRAP_METHOD,
    SIGN_TEST_TIE_POLICY,
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
        self.assertEqual(result["bootstrap_standard_error"], 0.0)
        self.assertEqual(result["wins"], 0)
        self.assertEqual(result["losses"], 0)
        self.assertEqual(result["ties"], 3)
        self.assertEqual(result["sign_test_non_ties"], 0)
        self.assertEqual(result["sign_test_tie_policy"], SIGN_TEST_TIE_POLICY)
        self.assertEqual(result["exact_sign_test_p"], 1.0)
        self.assertEqual(result["method"], BOOTSTRAP_METHOD)
        self.assertTrue(result["numpy_version"])

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
        self.assertEqual(result["sign_test_non_ties"], 3)

    def test_anchor_mismatch_fails_by_default(self):
        with self.assertRaisesRegex(ValueError, "anchor universe mismatch"):
            paired_bootstrap({"a": 0.0}, {"b": 1.0}, iterations=10)

    def test_intersection_is_explicit_and_reports_drops(self):
        result = paired_bootstrap(
            {"a": 0.0, "b": 0.5},
            {"b": 0.75, "c": 1.0},
            iterations=50,
            intersection=True,
        )
        self.assertEqual(result["entities"], 1)
        self.assertEqual(result["paired_mean_delta"], 0.25)
        self.assertEqual(
            result["alignment"],
            {
                "intersection_mode": True,
                "baseline_input_entities": 2,
                "candidate_input_entities": 2,
                "shared_entities": 1,
                "baseline_only_dropped": 1,
                "candidate_only_dropped": 1,
            },
        )

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
            baseline,
            candidate,
            metadata,
            ["country", "cardinality"],
            iterations=100,
            seed=3,
        )
        self.assertEqual(result["country"]["India"]["entities"], 2)
        self.assertEqual(result["country"]["US"]["entities"], 2)
        self.assertEqual(result["cardinality"]["0"]["entities"], 1)
        self.assertEqual(result["cardinality"]["2"]["entities"], 3)

    def test_exact_sign_test(self):
        self.assertEqual(exact_sign_test(0, 0), 1.0)
        self.assertEqual(exact_sign_test(1, 1), 1.0)
        self.assertEqual(exact_sign_test(3, 0), 0.25)

    def test_chunk_allocation_is_bounded_when_replicate_fits(self):
        baseline = {str(i): 0.25 for i in range(20)}
        candidate = {str(i): 0.5 for i in range(20)}
        result = paired_bootstrap(
            baseline,
            candidate,
            iterations=7,
            seed=5,
            chunk_size=256,
            max_draws_per_chunk=40,
        )
        self.assertEqual(result["bootstrap_effective_chunk_size"], 2)
        self.assertEqual(result["bootstrap_max_draws_per_chunk"], 40)
        self.assertEqual(result["bootstrap_delta_interval"], [0.25, 0.25])

    def test_chunk_allocation_is_bounded_when_one_replicate_exceeds_cap(self):
        baseline = {str(i): 0.25 for i in range(20)}
        candidate = {str(i): 0.5 for i in range(20)}
        result = paired_bootstrap(
            baseline,
            candidate,
            iterations=7,
            seed=5,
            max_draws_per_chunk=7,
        )
        self.assertEqual(result["bootstrap_effective_chunk_size"], 1)
        self.assertEqual(result["bootstrap_max_draws_per_chunk"], 7)
        self.assertEqual(result["bootstrap_delta_interval"], [0.25, 0.25])

    def test_chunk_partition_does_not_change_seeded_statistics(self):
        baseline = {str(i): 0.2 + (i % 5) * 0.1 for i in range(20)}
        candidate = {
            k: min(1.0, max(0.0, v + ((int(k) % 3) - 1) * 0.05))
            for k, v in baseline.items()
        }
        wide = paired_bootstrap(
            baseline,
            candidate,
            iterations=100,
            seed=517,
            max_draws_per_chunk=1000,
        )
        narrow = paired_bootstrap(
            baseline,
            candidate,
            iterations=100,
            seed=517,
            max_draws_per_chunk=7,
        )
        for key in (
            "bootstrap_delta_interval",
            "bootstrap_standard_error",
            "bootstrap_probability_delta_gt_0",
            "bootstrap_probability_delta_eq_0",
        ):
            self.assertEqual(wide[key], narrow[key])


if __name__ == "__main__":
    unittest.main()
