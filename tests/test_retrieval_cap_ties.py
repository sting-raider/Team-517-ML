import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "audit_cap_ties.py"
spec = importlib.util.spec_from_file_location("audit_cap_ties", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class RetrievalCapTieTests(unittest.TestCase):
    def test_id_permutation_changes_legacy_membership_at_boundary_tie(self):
        result = mod.audit()["boundary_crossing_tie"]
        self.assertEqual(result["legacy_count"], 160)
        self.assertEqual(result["legacy_membership_symmetric_difference_after_id_permutation"], 4)

    def test_boundary_tie_reference_is_id_invariant(self):
        result = mod.audit()["boundary_crossing_tie"]
        self.assertTrue(result["boundary_tie_invariant"])
        self.assertEqual(result["boundary_tie_count"], 163)
        self.assertEqual(result["boundary_tie_overflow"], 3)

    def test_no_boundary_tie_preserves_exact_legacy_membership(self):
        result = mod.audit()["no_boundary_tie"]
        self.assertTrue(result["legacy_invariant"])
        self.assertTrue(result["legacy_matches_boundary_tie_policy"])
        self.assertEqual(result["selected"], 160)

    def test_secondary_evidence_can_resolve_some_score_ties(self):
        result = mod.audit()["secondary_evidence"]
        self.assertEqual(result["score_only_count"], 163)
        self.assertEqual(result["score_hits_count"], 160)
        self.assertTrue(result["score_hits_exact_cap"])

    def test_invalid_cap_rejected(self):
        with self.assertRaises(ValueError):
            mod.legacy_exact_cap([], 0)
        with self.assertRaises(ValueError):
            mod.boundary_tie_cap([], 0)


if __name__ == "__main__":
    unittest.main()
