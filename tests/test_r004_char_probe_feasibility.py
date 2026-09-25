import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "experiments" / "r004_char_probe_feasibility.py"
SPEC = importlib.util.spec_from_file_location("r004", MODULE)
r004 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r004)


class R004FeasibilityTests(unittest.TestCase):
    def test_normalization_and_ngrams_are_deterministic(self):
        self.assertEqual(r004.norm_proxy("  Café--12/A  "), "cafe 12 a")
        self.assertEqual(r004.char_ngrams("Ab c"), {"abc"})
        self.assertIn("cafe", r004.char_ngrams("Café"))

    def test_keep_smallest_keeps_lowest_hash_ranks(self):
        heap = []
        for rank in (9, 2, 7, 1, 5):
            r004.keep_smallest(heap, 3, rank, (str(rank), "", "", "US"))
        self.assertEqual(sorted(-item[0] for item in heap), [1, 2, 5])

    def test_fold517_is_stable(self):
        expected = {
            "S1_000000001": "fit",
            "S1_000000002": "calibrate",
            "S1_000000003": "early",
            "S1_000000004": "fit",
        }
        self.assertEqual({key: r004.fold517(key) for key in expected}, expected)

    def test_cardinality_buckets(self):
        self.assertEqual(
            [r004.cardinality_bucket(x) for x in (0, 1, 2, 4, 5, 10)],
            ["0", "1", "2-4", "2-4", "5+", "5+"],
        )


if __name__ == "__main__":
    unittest.main()
