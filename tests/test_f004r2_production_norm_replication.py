import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "tools" / "experiments" / "f004r2_production_norm_replication.py"
spec = importlib.util.spec_from_file_location("f004r2", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class F004R2Tests(unittest.TestCase):
    def test_observed_unicode_domain_parity(self):
        samples = [
            "CafÂ\x80\x93 Road",
            "â\x80\x99 Avenue",
            "No ½ Block",
            "Ïndia ïndustrial",
            "¿ Test ¬ \x90",
        ]
        for value in samples:
            self.assertEqual(
                mod.f004_fallback_norm(value),
                mod.production_norm_emulation(value),
            )

    def test_collision_accounting(self):
        rows = [
            ["entity_id", "business_name", "business_address", "country"],
            ["a", "Alpha Shop", "12 Café Rd", "US"],
            ["b", "Beta Shop", "12 Cafe Rd", "US"],
            ["c", "Gamma", "44 Elsewhere", "US"],
            ["d", "One India", "9 Lane", "India"],
            ["e", "Two India", "9 Lane", "India"],
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "s1.tsv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle, delimiter="\t", lineterminator="\n").writerows(rows)
            result = mod.audit(path)
        self.assertEqual(
            result["normalization_parity"]["fallback_vs_production_semantics_mismatches"], 0
        )
        self.assertEqual(result["metrics"]["US"]["collision_groups"], 1)
        self.assertEqual(result["metrics"]["US"]["collision_records"], 2)
        self.assertEqual(result["metrics"]["US"]["cross_name_pairs"], 1)
        self.assertEqual(result["metrics"]["India"]["cross_name_pairs"], 1)
        self.assertFalse(result["protocol"]["entity_id_used_as_evidence"])


if __name__ == "__main__":
    unittest.main()
