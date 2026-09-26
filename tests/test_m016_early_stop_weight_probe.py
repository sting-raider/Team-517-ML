import importlib.util
import math
import unittest
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).parents[1] / "tools" / "experiments" / "m016_early_stop_weight_probe.py"
spec = importlib.util.spec_from_file_location("m016_early_stop_weight_probe", MODULE_PATH)
m016 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m016)


class M016ProbeTests(unittest.TestCase):
    def test_anchor_balanced_weights_equalize_group_mass(self):
        groups = np.array([0] + [1] * 7 + [2] * 160 + [3] * 43)
        weights = m016.anchor_balanced_row_weights(groups)
        masses = [weights[groups == group].sum() for group in range(4)]
        self.assertTrue(all(math.isclose(value, masses[0], rel_tol=0, abs_tol=1e-12) for value in masses))
        self.assertTrue(math.isclose(weights.mean(), 1.0, rel_tol=0, abs_tol=1e-12))

    def test_invalid_groups_fail_loud(self):
        with self.assertRaises(ValueError):
            m016.anchor_balanced_row_weights(np.array([]))
        with self.assertRaises(ValueError):
            m016.anchor_balanced_row_weights(np.zeros((2, 2)))

    def test_catboost_duplication_stress(self):
        unweighted_small = m016.train_once(1, False)
        unweighted_large = m016.train_once(190, False)
        weighted_small = m016.train_once(1, True)
        weighted_large = m016.train_once(190, True)
        self.assertNotEqual(unweighted_small["best_iteration"], unweighted_large["best_iteration"])
        self.assertEqual(weighted_small["best_iteration"], weighted_large["best_iteration"])
        self.assertEqual(weighted_small["tree_count"], weighted_large["tree_count"])


if __name__ == "__main__":
    unittest.main()
