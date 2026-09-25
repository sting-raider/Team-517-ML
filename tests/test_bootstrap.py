import tempfile
import unittest
from pathlib import Path

from ber.bootstrap import compare_tables, paired_entity_bootstrap, read_score_table


class PairedBootstrapTests(unittest.TestCase):
    def test_identical_scores_have_zero_delta(self):
        scores = {"a": 0.0, "b": 0.4, "c": 1.0}
        out = paired_entity_bootstrap(scores, scores, replicates=200, seed=7)
        self.assertEqual(out["observed_delta"], 0.0)
        self.assertEqual(out["percentile_interval"], [0.0, 0.0])
        self.assertEqual(out["bootstrap_standard_error"], 0.0)
        self.assertEqual(out["bootstrap_probability_delta_gt_zero"], 0.0)

    def test_constant_shift_is_exact(self):
        base = {"a": 0.1, "b": 0.2, "c": 0.3, "d": 0.4}
        cand = {k: v + 0.05 for k, v in base.items()}
        out = paired_entity_bootstrap(base, cand, replicates=300, seed=9)
        self.assertAlmostEqual(out["observed_delta"], 0.05)
        self.assertAlmostEqual(out["percentile_interval"][0], 0.05)
        self.assertAlmostEqual(out["percentile_interval"][1], 0.05)
        self.assertEqual(out["bootstrap_probability_delta_gt_zero"], 1.0)

    def test_deterministic_for_fixed_seed(self):
        base = {str(i): 0.2 + (i % 7) / 14 for i in range(50)}
        cand = {k: v + ((int(k) % 3) - 1) * 0.03 for k, v in base.items()}
        first = paired_entity_bootstrap(base, cand, replicates=400, seed=517)
        second = paired_entity_bootstrap(base, cand, replicates=400, seed=517)
        self.assertEqual(first, second)

    def test_anchor_universe_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "anchor universe mismatch"):
            paired_entity_bootstrap({"a": 0.5}, {"b": 0.5}, replicates=10)

    def test_mapping_anchor_collision_after_string_normalization_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate anchor after string normalization"):
            paired_entity_bootstrap({1: 0.5, "1": 0.6}, {"1": 0.5}, replicates=10)

    def test_duplicate_anchor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scores.tsv"
            path.write_text("anchor\trow_score\na\t0.5\na\t0.6\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate anchor"):
                read_score_table(path)

    def test_slice_results_and_slice_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base.tsv"
            cand = Path(tmp) / "cand.tsv"
            base.write_text(
                "anchor\trow_score\tcountry\na\t0.4\tIndia\nb\t0.6\tIndia\nc\t0.5\tUS\nd\t0.7\tUS\n",
                encoding="utf-8",
            )
            cand.write_text(
                "anchor\trow_score\tcountry\na\t0.3\tIndia\nb\t0.5\tIndia\nc\t0.7\tUS\nd\t0.9\tUS\n",
                encoding="utf-8",
            )
            out = compare_tables(base, cand, slice_col="country", replicates=100, seed=3)
            self.assertAlmostEqual(out["slices"]["India"]["observed_delta"], -0.1)
            self.assertAlmostEqual(out["slices"]["US"]["observed_delta"], 0.2)
            cand.write_text(
                "anchor\trow_score\tcountry\na\t0.3\tUS\nb\t0.5\tIndia\nc\t0.7\tUS\nd\t0.9\tUS\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "slice mismatch"):
                compare_tables(base, cand, slice_col="country", replicates=10)

    def test_rejects_nonfinite_and_out_of_range_scores(self):
        with self.assertRaisesRegex(ValueError, "not finite"):
            paired_entity_bootstrap({"a": float("nan")}, {"a": 0.5}, replicates=10)
        with self.assertRaisesRegex(ValueError, "outside"):
            paired_entity_bootstrap({"a": -0.1}, {"a": 0.5}, replicates=10)


if __name__ == "__main__":
    unittest.main()
