import math
import unittest

from ber.frequency_cliff import (
    cliff,
    current_contribution,
    family_aware_contribution,
    smooth_contribution,
    synthetic_rank_score,
)


class FrequencyCliffTests(unittest.TestCase):
    def test_exact_name_has_hard_1000_to_1001_cliff(self):
        at_boundary = current_contribution("n:", 1000)
        self.assertIsNotNone(at_boundary)
        self.assertAlmostEqual(at_boundary, 59.21034047197618, places=10)
        self.assertIsNone(current_contribution("n:", 1001))

    def test_smooth_formula_barely_changes_across_boundary(self):
        delta = smooth_contribution("n:", 1000) - smooth_contribution("n:", 1001)
        self.assertGreater(delta, 0.0)
        self.assertLess(delta, 0.0011)

        measured = cliff("n:")
        self.assertAlmostEqual(measured.smooth_delta, delta, places=12)
        self.assertGreater(measured.actual_drop, 59.0)

    def test_exact_address_cliff_is_also_large(self):
        measured = cliff("a:")
        self.assertGreater(measured.actual_drop, 49.0)
        self.assertLess(measured.smooth_delta, 0.0011)

    def test_cutoff_can_invert_rank_with_same_other_evidence(self):
        distractor = 20.0
        just_inside = synthetic_rank_score(
            5.0, exact_kind="n:", exact_freq=1000
        )
        just_outside = synthetic_rank_score(
            5.0, exact_kind="n:", exact_freq=1001
        )
        self.assertGreater(just_inside, distractor)
        self.assertLess(just_outside, distractor)

    def test_family_aware_variant_is_opt_in_only(self):
        self.assertIsNone(current_contribution("n:", 1001))
        restored = family_aware_contribution(
            "n:", 1001, max_freq_by_kind={"n:": 2000}
        )
        self.assertAlmostEqual(restored, smooth_contribution("n:", 1001))
        self.assertIsNone(
            family_aware_contribution(
                "w:", 1001, max_freq_by_kind={"n:": 2000}
            )
        )

    def test_invalid_frequency_fails_loudly(self):
        with self.assertRaises(ValueError):
            current_contribution("n:", 0)


if __name__ == "__main__":
    unittest.main()
