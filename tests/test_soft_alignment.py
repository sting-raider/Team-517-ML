import unittest

from ber.features import (
    FEATURE_NAMES,
    FEATURE_NAMES_SOFT_ALIGNMENT,
    features,
    features_with_soft_alignment,
)
from ber.soft_alignment import (
    ADDRESS_SOFT_ALIGNMENT_FEATURE_NAMES,
    address_soft_alignment_features,
)


class SoftAlignmentTests(unittest.TestCase):
    def test_empty_is_not_rewarded(self):
        self.assertEqual(address_soft_alignment_features("", ""), [0.0] * 5)
        self.assertEqual(address_soft_alignment_features("12 road", ""), [0.0] * 5)

    def test_reordered_exact_tokens(self):
        got = address_soft_alignment_features("12 mg road", "road mg 12")
        self.assertEqual(got, [1.0] * 5)

    def test_duplicate_token_cannot_be_reused(self):
        left, right, hmean, strong, exact = address_soft_alignment_features(
            "road road 12", "road 12"
        )
        self.assertAlmostEqual(left, 2 / 3)
        self.assertAlmostEqual(right, 1.0)
        self.assertAlmostEqual(hmean, 0.8)
        self.assertAlmostEqual(strong, 2 / 3)
        self.assertAlmostEqual(exact, 2 / 3)

    def test_numeric_mismatch_is_not_fuzzy(self):
        got = address_soft_alignment_features("12 road", "13 road")
        self.assertEqual(got, [0.5, 0.5, 0.5, 0.5, 0.5])

    def test_typo_gets_soft_credit(self):
        exact = address_soft_alignment_features(
            "mahatma gandhi road", "road gandhi mahatma"
        )
        typo = address_soft_alignment_features(
            "mahatma gandhi road", "raod gandhi mahatma"
        )
        unrelated = address_soft_alignment_features(
            "mahatma gandhi road", "airport tower block"
        )
        self.assertEqual(exact, [1.0] * 5)
        self.assertGreater(typo[2], 0.85)
        self.assertGreater(typo[2], unrelated[2])
        self.assertLess(typo[4], exact[4])

    def test_swap_changes_only_directional_coverages(self):
        ab = address_soft_alignment_features("main market road", "main road")
        ba = address_soft_alignment_features("main road", "main market road")
        self.assertAlmostEqual(ab[0], ba[1])
        self.assertAlmostEqual(ab[1], ba[0])
        self.assertEqual(ab[2:], ba[2:])

    def test_outputs_are_bounded(self):
        got = address_soft_alignment_features(
            "42 industrial estate phase two", "industrial est phase 2 plot 42"
        )
        self.assertTrue(all(0.0 <= value <= 1.0 for value in got))

    def test_deterministic(self):
        left = "sector sector five market road"
        right = "market rd sector five"
        self.assertEqual(
            address_soft_alignment_features(left, right),
            address_soft_alignment_features(left, right),
        )

    def test_legacy_schema_and_values_are_unchanged(self):
        args = (
            "alpha store",
            "12 mg road",
            "alfa store",
            "road mg 12",
            7.5,
            3,
            2,
        )
        legacy = features(*args)
        extended = features_with_soft_alignment(*args)
        self.assertEqual(len(FEATURE_NAMES), 47)
        self.assertEqual(len(ADDRESS_SOFT_ALIGNMENT_FEATURE_NAMES), 5)
        self.assertEqual(len(FEATURE_NAMES_SOFT_ALIGNMENT), 52)
        self.assertEqual(legacy, extended[:47])
        self.assertEqual(FEATURE_NAMES_SOFT_ALIGNMENT[:47], FEATURE_NAMES)


if __name__ == "__main__":
    unittest.main()
