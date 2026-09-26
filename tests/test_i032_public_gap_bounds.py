import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "tools" / "experiments" / "i032_public_gap_bounds.py"
spec = importlib.util.spec_from_file_location("i032", MODULE_PATH)
i032 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(i032)


class I032Tests(unittest.TestCase):
    def test_group_score_identity_round_trip(self):
        overall = 0.917
        weight = 0.15
        other = 0.946
        group = i032.required_group_score(overall, weight, other)
        self.assertAlmostEqual(weight * group + (1 - weight) * other, overall, places=14)
        recovered = i032.required_other_score(overall, weight, group)
        self.assertAlmostEqual(recovered, other, places=14)

    def test_two_sample_hoeffding_monotone_in_second_sample(self):
        delta = 0.033
        p_small = i032.two_sample_hoeffding_bound(delta, 5000, 1000)
        p_large = i032.two_sample_hoeffding_bound(delta, 5000, 5000)
        self.assertLess(p_large, p_small)
        n = i032.minimum_second_sample_for_hoeffding(delta, 5000, 0.05)
        self.assertIsNotNone(n)
        self.assertLessEqual(i032.two_sample_hoeffding_bound(delta, 5000, n), 0.05)
        if n > 1:
            self.assertGreater(i032.two_sample_hoeffding_bound(delta, 5000, n - 1), 0.05)

    def test_stream_country_scan(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tiny.tsv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh, delimiter="\t", lineterminator="\n")
                w.writerow(["entity_id", "business_name", "business_address", "country"])
                w.writerow(["S1_1", "a", "x", "US"])
                w.writerow(["S1_2", "b", "y", "France"])
                w.writerow(["S1_3", "c", "z", "US"])
            rows, counts, digest = i032.scan_country_counts(path)
            self.assertEqual(rows, 3)
            self.assertEqual(counts, {"France": 1, "US": 2})
            self.assertEqual(len(digest), 64)

    def test_full_analysis_counterfactual_recomposes(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            tsv = td / "test.tsv"
            with tsv.open("w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh, delimiter="\t", lineterminator="\n")
                w.writerow(["entity_id", "business_name", "business_address", "country"])
                for i, country in enumerate(["France", "India", "India", "US"]):
                    w.writerow([f"S1_{i}", "a", "b", country])
            confirm = {
                "new": {
                    "all": {"macro_f0_5": 0.95, "entities": 5000},
                    "India": {"macro_f0_5": 0.93},
                    "US": {"macro_f0_5": 0.97},
                },
                "paired_comparison": {"bootstrap_95_interval": [0.005, 0.01]},
            }
            current = {
                "new": {
                    "calibrate": {"all": {"macro_f0_5": 0.949}},
                    "holdout": {"all": {"macro_f0_5": 0.945}},
                }
            }
            (td / "c.json").write_text(json.dumps(confirm), encoding="utf-8")
            (td / "i.json").write_text(json.dumps(current), encoding="utf-8")
            out = i032.analyze(tsv, td / "c.json", td / "i.json", 0.917)
            cf = out["full_test_mix_counterfactual"]
            self.assertTrue(cf["france_only_explanation_is_arithmetically_possible"])
            w_f = cf["france_weight"]
            s_nf = cf["non_france_confirmation_score_reweighted_to_test_india_us_mix"]
            s_f = cf["required_france_score_for_reported_public_if_non_france_unchanged"]
            self.assertAlmostEqual(w_f * s_f + (1 - w_f) * s_nf, 0.917, places=14)


if __name__ == "__main__":
    unittest.main()
