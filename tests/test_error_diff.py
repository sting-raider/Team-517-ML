import json
import tempfile
import unittest
from pathlib import Path

from ber.error_diff import compare_rows, load_rows, make_rows, write_rows


class ErrorDiffTests(unittest.TestCase):
    def test_paired_diff_and_slices(self):
        baseline = [
            {"anchor": "a", "score": 1.0, "country": "US", "truth_count": 0},
            {"anchor": "b", "score": 0.5, "country": "US", "truth_count": 1},
            {"anchor": "c", "score": 0.4, "country": "India", "truth_count": 2},
        ]
        challenger = [
            {"anchor": "a", "score": 1.0, "country": "US", "truth_count": 0},
            {"anchor": "b", "score": 0.7, "country": "US", "truth_count": 1},
            {"anchor": "c", "score": 0.2, "country": "India", "truth_count": 2},
        ]
        report = compare_rows(baseline, challenger)
        self.assertTrue(report["universe"]["exact_anchor_match"])
        self.assertEqual(report["overall"]["improved"], 1)
        self.assertEqual(report["overall"]["regressed"], 1)
        self.assertEqual(report["overall"]["unchanged"], 1)
        self.assertAlmostEqual(report["overall"]["delta"], 0.0)
        self.assertAlmostEqual(report["slices"]["country"]["US"]["delta"], 0.1)
        self.assertAlmostEqual(
            report["slices"]["cardinality"]["two_to_three"]["delta"], -0.2
        )

    def test_anchor_mismatch_fails_loudly(self):
        baseline = [{"anchor": "a", "score": 1.0}, {"anchor": "b", "score": 0.0}]
        challenger = [{"anchor": "b", "score": 1.0}, {"anchor": "c", "score": 0.0}]
        with self.assertRaisesRegex(ValueError, "Anchor-set mismatch"):
            compare_rows(baseline, challenger)
        report = compare_rows(baseline, challenger, allow_intersection=True)
        self.assertFalse(report["universe"]["exact_anchor_match"])
        self.assertEqual(report["universe"]["compared_entities"], 1)
        self.assertEqual(report["universe"]["only_baseline_count"], 1)
        self.assertEqual(report["universe"]["only_challenger_count"], 1)

    def test_truth_metadata_mismatch_fails(self):
        baseline = [{"anchor": "a", "score": 1.0, "truth_count": 1}]
        challenger = [{"anchor": "a", "score": 1.0, "truth_count": 2}]
        with self.assertRaisesRegex(ValueError, "Invariant metadata mismatch"):
            compare_rows(baseline, challenger)

    def test_make_write_and_load_rows(self):
        truth = {"a": [], "b": ["x", "y"]}
        predicted = {"a": ["z"], "b": ["x"]}
        candidates = {"a": ["z"], "b": ["x", "bad"]}
        metadata = {"a": {"country": "US"}, "b": {"country": "India"}}
        rows = make_rows(truth, predicted, candidates, metadata)
        self.assertEqual(rows[0]["score"], 0.0)
        self.assertAlmostEqual(rows[1]["score"], 1.25 / 1.5)
        self.assertEqual(rows[1]["candidate_count"], 2)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            write_rows(path, rows)
            loaded = load_rows(path)
        self.assertEqual(loaded, rows)

    def test_json_object_rows_loader_and_duplicate_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.json"
            path.write_text(json.dumps({"rows": [{"anchor": "a", "score": 1}]}))
            self.assertEqual(load_rows(path)[0]["score"], 1.0)
            path.write_text(json.dumps([
                {"anchor": "a", "score": 1},
                {"anchor": "a", "score": 0},
            ]))
            with self.assertRaisesRegex(ValueError, "Duplicate anchor"):
                load_rows(path)


if __name__ == "__main__":
    unittest.main()
