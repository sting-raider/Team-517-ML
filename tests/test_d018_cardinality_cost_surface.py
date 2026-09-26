import importlib.util
import tempfile
import unittest
from collections import Counter
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "experiments"
    / "d018_cardinality_cost_surface.py"
)
SPEC = importlib.util.spec_from_file_location("d018_cardinality_cost_surface", MODULE_PATH)
d018 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d018)


class D018Tests(unittest.TestCase):
    def test_metric_parity_known_sets(self):
        self.assertEqual(d018.row_score_from_counts(0, 0, 0), 1.0)
        self.assertEqual(d018.row_score_from_counts(0, 0, 1), 0.0)
        self.assertAlmostEqual(
            d018.row_score_from_counts(3, 2, 1),
            2.5 / (0.75 + 3),
        )
        self.assertEqual(d018.row_score_from_counts(1, 0, 0), 0.0)

    def test_one_fp_vs_fn_switches_after_cardinality_one(self):
        metrics = d018.summarize_hist(Counter({0: 1, 1: 1, 2: 1, 3: 1}))
        costs = metrics["one_error_cost_by_cardinality"]
        self.assertLess(costs["1"]["one_fp_loss"], costs["1"]["one_fn_loss"])
        self.assertGreater(costs["2"]["one_fp_loss"], costs["2"]["one_fn_loss"])
        self.assertGreater(costs["3"]["one_fp_loss"], costs["3"]["one_fn_loss"])

    def test_hard_cap_is_monotone_and_reaches_one(self):
        metrics = d018.summarize_hist(Counter({0: 2, 1: 3, 2: 4, 7: 5}))
        values = [
            metrics["hard_cap_perfect_ranking_macro_f0_5"][str(cap)]
            for cap in range(1, 11)
        ]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[-1], 1.0)

    def test_percentiles_from_hist(self):
        hist = Counter({0: 1, 1: 2, 4: 1})
        self.assertEqual(d018.percentile_from_hist(hist, 0.50), 1)
        self.assertEqual(d018.percentile_from_hist(hist, 0.75), 1)
        self.assertEqual(d018.percentile_from_hist(hist, 1.0), 4)

    def test_audit_small_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source1 = root / "source1.tsv"
            truth = root / "truth.tsv"
            source1.write_text(
                "entity_id\tbusiness_name\tbusiness_address\tcountry\n"
                "A\tn\ta\tUS\n"
                "B\tn\ta\tIndia\n"
                "C\tn\ta\tUS\n",
                encoding="utf-8",
            )
            truth.write_text(
                "source1_entity_id\tmatched_entity_ids\n"
                "A\t\n"
                "B\tS2-x\n"
                "C\tS2-y,S3-z\n",
                encoding="utf-8",
            )
            result = d018.audit(source1, truth)
            self.assertEqual(result["cardinality_histogram"], {"0": 1, "1": 1, "2": 1})
            self.assertEqual(result["countries"]["US"]["anchors"], 2)
            self.assertEqual(result["countries"]["India"]["anchors"], 1)

    def test_duplicate_source1_fails_loud(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source1 = root / "source1.tsv"
            truth = root / "truth.tsv"
            source1.write_text(
                "entity_id\tbusiness_name\tbusiness_address\tcountry\n"
                "A\tn\ta\tUS\n"
                "A\tn\ta\tUS\n",
                encoding="utf-8",
            )
            truth.write_text(
                "source1_entity_id\tmatched_entity_ids\n"
                "A\t\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate Source-1"):
                d018.audit(source1, truth)


if __name__ == "__main__":
    unittest.main(verbosity=2)
