import math
import unittest

from tools.i024_v2_feature_reference import (
    dense_desc_rank,
    extra_rows,
    frequency_tables,
    minimum_blocker_hit_score,
)


class I024ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.inventory = [
            {"source": 1, "country": "US", "n": "alpha", "a": "12 main"},
            {"source": 1, "country": "US", "n": "alpha", "a": ""},
            {"source": 1, "country": "IN", "n": "alpha", "a": "12 main"},
            {"source": 2, "country": "US", "n": "beta", "a": "7 road"},
            {"source": 3, "country": "US", "n": "beta", "a": "7 road"},
            {"source": 2, "country": "IN", "n": "beta", "a": "7 road"},
        ]

    def test_country_local_and_target_sources_pooled(self):
        f = frequency_tables(self.inventory)
        self.assertEqual(f[("left", "n")][("US", "alpha")], 2)
        self.assertEqual(f[("left", "n")][("IN", "alpha")], 1)
        self.assertEqual(f[("right", "n")][("US", "beta")], 2)
        self.assertEqual(f[("right", "n")][("IN", "beta")], 1)
        self.assertNotIn(("US", ""), f[("left", "a")])

    def test_dense_rank_ties_are_id_order_invariant(self):
        scores = [20.0, 10.0, 20.0, 5.0]
        self.assertEqual(dense_desc_rank(scores), [1, 2, 1, 3])
        perm = [2, 0, 3, 1]
        perm_ranks = dense_desc_rank([scores[i] for i in perm])
        restored = [None] * 4
        for idx, original in enumerate(perm):
            restored[original] = perm_ranks[idx]
        self.assertEqual(restored, [1, 2, 1, 3])

    def test_relative_score_and_frequency_features(self):
        f = frequency_tables(self.inventory)
        anchor = self.inventory[0]
        targets = [self.inventory[3], self.inventory[4]]
        rows = extra_rows(anchor, targets, [25.0, 25.0], f)
        self.assertEqual(rows[0], rows[1])
        self.assertAlmostEqual(rows[0][0], math.log(3))
        self.assertAlmostEqual(rows[0][2], math.log(3))
        self.assertAlmostEqual(rows[0][4], math.log(2))
        self.assertEqual(rows[0][5], 1.0)

    def test_blocker_score_never_hits_relative_denominator_floor(self):
        self.assertGreater(minimum_blocker_hit_score(), 9.21)
        self.assertGreater(minimum_blocker_hit_score(), 1.0)

    def test_identical_split_inventory_has_identical_semantics(self):
        f_train = frequency_tables(self.inventory)
        f_test = frequency_tables([dict(r) for r in self.inventory])
        self.assertEqual(f_train, f_test)
        anchor = self.inventory[0]
        targets = [self.inventory[3], self.inventory[4]]
        self.assertEqual(
            extra_rows(anchor, targets, [30.0, 12.0], f_train),
            extra_rows(anchor, targets, [30.0, 12.0], f_test),
        )


if __name__ == "__main__":
    unittest.main()
