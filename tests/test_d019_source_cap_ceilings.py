import importlib.util
import tempfile
import unittest
from collections import Counter
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "experiments"
    / "d019_source_cap_ceilings.py"
)
SPEC = importlib.util.spec_from_file_location("d019_source_cap_ceilings", MODULE_PATH)
d019 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d019)


class D019Tests(unittest.TestCase):
    def test_global_dominates_same_budget_source_caps(self):
        result = d019.summarize(
            Counter({(0, 0): 1, (2, 0): 1, (0, 2): 1, (2, 2): 1}),
            3,
        )
        for key, value in result["source_cap_surface"].items():
            cap2, cap3 = map(int, key.split(","))
            self.assertLessEqual(
                value["score"],
                result["global_caps"][str(cap2 + cap3)] + 1e-12,
            )

    def test_balanced_split_can_beat_lopsided_at_same_budget(self):
        result = d019.summarize(Counter({(1, 2): 10}), 3)
        self.assertGreater(
            result["source_cap_surface"]["1,1"]["score"],
            result["source_cap_surface"]["2,0"]["score"],
        )

    def test_singleton_scores_one_under_caps(self):
        result = d019.summarize(Counter({(0, 0): 5}), 2)
        self.assertTrue(all(value == 1.0 for value in result["global_caps"].values()))
        self.assertTrue(
            all(
                value["score"] == 1.0
                for value in result["source_cap_surface"].values()
            )
        )

    def test_small_file_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source1 = root / "source1.tsv"
            truth = root / "truth.tsv"
            source1.write_text(
                "entity_id\tbusiness_name\tbusiness_address\tcountry\n"
                "A\tn\ta\tUS\n"
                "B\tn\ta\tIndia\n",
                encoding="utf-8",
            )
            truth.write_text(
                "source1_entity_id\tmatched_entity_ids\n"
                "A\tS2-x,S3-y\n"
                "B\tS3-z\n",
                encoding="utf-8",
            )
            result = d019.audit(source1, truth, 2)
            self.assertEqual(
                result["joint_source_cardinality_histogram"],
                {"0,1": 1, "1,1": 1},
            )

    def test_unknown_source_prefix_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source1 = root / "source1.tsv"
            truth = root / "truth.tsv"
            source1.write_text(
                "entity_id\tbusiness_name\tbusiness_address\tcountry\n"
                "A\tn\ta\tUS\n",
                encoding="utf-8",
            )
            truth.write_text(
                "source1_entity_id\tmatched_entity_ids\n"
                "A\tS4-x\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unknown target source"):
                d019.audit(source1, truth, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
