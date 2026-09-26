import importlib.util
import math
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "tools" / "experiments" / "m015_anchor_weight_audit.py"
spec = importlib.util.spec_from_file_location("m015_anchor_weight_audit", MODULE_PATH)
m015 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m015)


class M015AuditTests(unittest.TestCase):
    def test_inverse_count_weighting_equalizes_anchor_mass(self):
        masses = m015.anchor_mass_from_inverse_count_weights([1, 7, 160, 43])
        self.assertTrue(all(math.isclose(value, masses[0], rel_tol=0, abs_tol=1e-12) for value in masses))
        self.assertTrue(math.isclose(sum(masses), 211.0, rel_tol=0, abs_tol=1e-12))

    def test_invalid_candidate_counts_fail_loud(self):
        for counts in ([], [0], [1, 0, 2], [-1, 3]):
            with self.assertRaises(ValueError):
                m015.anchor_mass_from_inverse_count_weights(counts)

    def test_fold_is_deterministic(self):
        ids = ["S1-925783039", "S1-773889195", "S1-965667"]
        self.assertEqual([m015.fold517(x) for x in ids], [m015.fold517(x) for x in ids])
        self.assertTrue(all(m015.fold517(x) in {"fit", "early", "calibrate", "holdout"} for x in ids))

    def test_fit_window_excludes_consumed_gap(self):
        fit_id = next(
            f"S1-synthetic-{i}"
            for i in range(1000)
            if m015.fold517(f"S1-synthetic-{i}") == "fit"
        )
        self.assertTrue(m015.in_int003_fit(30_000, fit_id))
        self.assertFalse(m015.in_int003_fit(30_001, fit_id))
        self.assertFalse(m015.in_int003_fit(50_000, fit_id))
        self.assertTrue(m015.in_int003_fit(50_001, fit_id))
        self.assertTrue(m015.in_int003_fit(200_000, fit_id))
        self.assertFalse(m015.in_int003_fit(200_001, fit_id))


if __name__ == "__main__":
    unittest.main()
