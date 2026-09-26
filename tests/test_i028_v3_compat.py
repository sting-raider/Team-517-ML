import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "ber" / "v3_compat.py"
spec = importlib.util.spec_from_file_location("v3_compat", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class V3CompatibilityTests(unittest.TestCase):
    def test_restores_v2_floor_for_rrf_scores_below_one(self):
        names = ["retrieval", "other", "relative_retrieval_score"]
        x = np.array([[.024, 7, 1.0], [.012, 8, .5], [.020, 9, 1.0]], dtype=np.float32)
        groups = np.array([0, 0, 1])
        out = mod.v2_prefix_from_v3(x, groups, names)
        np.testing.assert_allclose(out[:, 2], [.024, .012, .020], rtol=0, atol=1e-7)
        np.testing.assert_allclose(out[:, 0], x[:, 0])

    def test_preserves_v2_ratio_when_top_exceeds_one(self):
        names = ["retrieval", "relative_retrieval_score"]
        x = np.array([[10.0, 1.0], [5.0, .5]], dtype=np.float32)
        out = mod.v2_prefix_from_v3(x, np.array([4, 4]), names)
        np.testing.assert_allclose(out[:, 1], [1.0, .5])

    def test_rejects_misaligned_groups(self):
        with self.assertRaises(ValueError):
            mod.v2_prefix_from_v3(
                np.zeros((2, 2)), np.array([0]),
                ["retrieval", "relative_retrieval_score"],
            )


if __name__ == "__main__":
    unittest.main()
