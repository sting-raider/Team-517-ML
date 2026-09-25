import unittest
import numpy as np

from ber.candidate_budget_contract import raw_retrieval_rank


class CandidateBudgetContractTests(unittest.TestCase):
    def test_matches_retrieval_desc_target_asc_within_group(self):
        groups = np.array([0, 0, 0, 0, 1, 1])
        targets = np.array(["z", "b", "a", "c", "x", "w"])
        retrieval = np.array([1.0, 3.0, 3.0, 2.0, 5.0, 5.0], dtype=np.float32)
        rank = raw_retrieval_rank(groups, targets, retrieval)
        self.assertEqual(rank.tolist(), [4, 2, 1, 3, 2, 1])

    def test_rank_restarts_for_each_anchor(self):
        groups = np.array([2, 2, 7, 7])
        targets = np.array(["b", "a", "b", "a"])
        retrieval = np.array([1.0, 2.0, 1.0, 2.0], dtype=np.float32)
        self.assertEqual(raw_retrieval_rank(groups, targets, retrieval).tolist(), [2, 1, 2, 1])

    def test_caps_are_nested(self):
        groups = np.array([0, 0, 0, 1, 1, 1])
        targets = np.array(["a", "b", "c", "d", "e", "f"])
        retrieval = np.array([3, 2, 1, 3, 2, 1], dtype=np.float32)
        rank = raw_retrieval_rank(groups, targets, retrieval)
        self.assertTrue(np.all((rank <= 1) <= (rank <= 2)))
        self.assertTrue(np.all((rank <= 2) <= (rank <= 3)))

    def test_empty_inputs(self):
        rank = raw_retrieval_rank([], [], [])
        self.assertEqual(rank.dtype, np.int32)
        self.assertEqual(rank.size, 0)

    def test_length_mismatch_fails_loudly(self):
        with self.assertRaises(ValueError):
            raw_retrieval_rank([0], ["a", "b"], [1.0])


if __name__ == "__main__":
    unittest.main()
