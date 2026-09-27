import unittest

from tools.experiments.r032_neural_cap_headroom import combine_variant, calibration_pick


class R032Tests(unittest.TestCase):
    def test_weighted_pair_and_anchor_macro(self):
        india = {
            "anchors": 2,
            "variants": {
                "cap32_dense16": {
                    "candidate_pair_recall": .5,
                    "blocking_oracle_macro_f0_5": .8,
                }
            },
        }
        us = {
            "anchors": 3,
            "variants": {
                "cap32_dense16": {
                    "candidate_pair_recall": 1.0,
                    "blocking_oracle_macro_f0_5": .9,
                }
            },
        }
        row = combine_variant(india, us, {"India": 4, "US": 6}, "cap32_dense16")
        self.assertAlmostEqual(row["candidate_pair_recall"], .8)
        self.assertAlmostEqual(row["blocking_oracle_macro_f0_5"], .86)

    def test_calibration_pick_is_per_cap(self):
        rows = [
            {"cap": 32, "dense": 8, "blocking_oracle_macro_f0_5": .9},
            {"cap": 32, "dense": 16, "blocking_oracle_macro_f0_5": .91},
            {"cap": 64, "dense": 16, "blocking_oracle_macro_f0_5": .92},
        ]
        picked = calibration_pick(rows)
        self.assertEqual(picked[32]["dense"], 16)
        self.assertEqual(picked[64]["dense"], 16)

    def test_tie_prefers_smaller_dense_allocation(self):
        rows = [
            {"cap": 64, "dense": 32, "blocking_oracle_macro_f0_5": .92},
            {"cap": 64, "dense": 16, "blocking_oracle_macro_f0_5": .92},
        ]
        self.assertEqual(calibration_pick(rows)[64]["dense"], 16)


if __name__ == "__main__":
    unittest.main()
