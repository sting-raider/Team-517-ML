import unittest

import numpy as np

from ber.capped_match import compose_dense_gate_blank_recovery


class DenseGateBlankRecoveryTest(unittest.TestCase):
    def test_recovery_is_applied_after_gate(self):
        # Pair 0 is dense, selected by V5, removed by the stricter gate, and
        # eligible for INT007. The combined rule must re-add it.
        cutoff=np.log(.95/.05)
        result=compose_dense_gate_blank_recovery(
            np.array([cutoff+.25, cutoff+1.0, cutoff-.5]),
            np.array([True, False, False]), .95, .5,
            np.array([True, False, True]))
        self.assertTrue(result['base_selected'][0])
        self.assertFalse(result['gated_selected'][0])
        self.assertTrue(result['readded_gate_removed'][0])
        self.assertTrue(result['final_selected'][0])
        self.assertTrue(result['final_selected'][1])
        self.assertTrue(result['final_selected'][2])

    def test_noneligible_gate_removal_stays_removed(self):
        cutoff=np.log(.95/.05)
        result=compose_dense_gate_blank_recovery(
            np.array([cutoff+.1]), np.array([True]), .95, .5,
            np.array([False]))
        self.assertTrue(result['base_selected'][0])
        self.assertFalse(result['gated_selected'][0])
        self.assertFalse(result['recovered'][0])
        self.assertFalse(result['final_selected'][0])

    def test_original_int007_addition_is_preserved(self):
        cutoff=np.log(.95/.05)
        result=compose_dense_gate_blank_recovery(
            np.array([cutoff-1.0]), np.array([False]), .95, .5,
            np.array([True]))
        self.assertFalse(result['base_selected'][0])
        self.assertTrue(result['recovered'][0])
        self.assertFalse(result['readded_gate_removed'][0])
        self.assertTrue(result['final_selected'][0])

    def test_shape_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            compose_dense_gate_blank_recovery(
                np.zeros(2), np.zeros(1,dtype=bool), .95, .5,
                np.zeros(2,dtype=bool))

    def test_invalid_threshold_fails_closed(self):
        with self.assertRaises(ValueError):
            compose_dense_gate_blank_recovery(
                np.zeros(1), np.zeros(1,dtype=bool), 1.0, .5,
                np.zeros(1,dtype=bool))


if __name__ == '__main__':
    unittest.main()
