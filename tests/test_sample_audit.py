import unittest

from ber.sample_audit import _effects, fold, proportion_z


class SampleAuditTests(unittest.TestCase):
    def test_fold_is_deterministic_and_valid(self):
        self.assertEqual(fold("S1-test"), fold("S1-test"))
        self.assertIn(fold("S1-test"), {"fit", "early", "calibrate", "holdout"})

    def test_proportion_z_direction(self):
        self.assertGreater(proportion_z(.06, .05, 1000), 0)
        self.assertLess(proportion_z(.04, .05, 1000), 0)
        self.assertEqual(proportion_z(.05, .05, 1000), 0)

    def test_effects_include_singleton_and_country_slices(self):
        population = {
            "n": 10000,
            "singleton_rate": .05,
            "name_missing_rate": 0.0,
            "address_missing_rate": 0.0,
            "country_share": {"US": .6, "India": .4},
            "truth_cardinality_distribution": {"0": .05, "1": .05, "2": .2, "3": .25, "4": .2, "5+": .25},
            "mean_truth_cardinality": 3.5,
            "truth_cardinality_sd": 1.5,
            "name_len": {"mean": 20.0, "sd": 5.0},
            "address_len": {"mean": 40.0, "sd": 10.0},
            "name_tokens": {"mean": 3.0, "sd": 1.0},
            "address_tokens": {"mean": 7.0, "sd": 2.0},
            "by_country": {
                "US": {"n": 6000, "singleton_rate": .05, "mean_truth_cardinality": 3.5},
                "India": {"n": 4000, "singleton_rate": .05, "mean_truth_cardinality": 3.5},
            },
        }
        sample = {
            **population,
            "n": 1000,
            "singleton_rate": .06,
            "country_share": {"US": .59, "India": .41},
            "by_country": {
                "US": {"n": 590, "singleton_rate": .05, "mean_truth_cardinality": 3.5},
                "India": {"n": 410, "singleton_rate": .07, "mean_truth_cardinality": 3.5},
            },
        }
        out = _effects(sample, population)
        self.assertAlmostEqual(out["singleton_rate"]["delta_pp"], 1.0)
        self.assertGreater(out["singleton_rate"]["z_hash_random"], 0)
        self.assertAlmostEqual(out["country_share.India"]["delta_pp"], 1.0)
        self.assertAlmostEqual(out["singleton_rate.India"]["delta_pp"], 2.0)


if __name__ == "__main__":
    unittest.main()
