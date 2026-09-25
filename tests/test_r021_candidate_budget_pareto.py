import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "tools"
    / "experiments"
    / "r021_candidate_budget_pareto.py"
)
spec = importlib.util.spec_from_file_location("r021", MODULE_PATH)
r021 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(r021)


class R021Tests(unittest.TestCase):
    def _write_fixture(self, root: Path):
        reports = root / "reports"
        reports.mkdir()
        candidate = {
            "entities": 10,
            "singleton_count": 2,
            "all_empty_baseline": 0.2,
            "candidate_pair_recall": 0.9,
            "candidate_entity_recall": 0.9,
            "all_matches_retrieved_rate": 0.8,
            "blocking_oracle_macro_f0_5": 0.97,
            "candidate_count_quantiles": {
                "p50": 60.0,
                "p90": 70.0,
                "p99": 78.0,
                "max": 80.0,
            },
        }
        wide = {
            "retrieval_80": {
                **candidate,
                "macro_f0_5": 0.91,
                "singleton_false_positive_rate": 0.1,
                "candidate_count_quantiles": {
                    "p50": 80.0,
                    "p90": 80.0,
                    "p99": 80.0,
                    "max": 80.0,
                },
            },
            "lexical_80": {
                **candidate,
                "macro_f0_5": 0.92,
                "singleton_false_positive_rate": 0.1,
            },
            "lexical_640": {
                **candidate,
                "macro_f0_5": 0.93,
                "singleton_false_positive_rate": 0.2,
                "candidate_pair_recall": 0.95,
                "candidate_entity_recall": 0.95,
                "all_matches_retrieved_rate": 0.85,
                "blocking_oracle_macro_f0_5": 0.98,
                "candidate_count_quantiles": {
                    "p50": 600.0,
                    "p90": 640.0,
                    "p99": 640.0,
                    "max": 640.0,
                },
            },
        }
        retrieval = {
            k: {
                m: v
                for m, v in s.items()
                if m not in ("macro_f0_5", "singleton_false_positive_rate")
            }
            for k, s in wide.items()
        }
        tuning = {
            "depth10": {
                "macro_f0_5": 0.94,
                "threshold": 0.625,
                "candidate_count_quantiles": {
                    "p50": 600.0,
                    "p90": 640.0,
                    "p99": 640.0,
                    "max": 640.0,
                },
            }
        }
        data = {
            "test": [
                {"source": 1, "country": "US", "records": 7},
                {"source": 1, "country": "India", "records": 3},
            ]
        }
        for name, obj in [
            ("wide_calibration.json", wide),
            ("retrieval_study.json", retrieval),
            ("tuning.json", tuning),
            ("data_audit.json", data),
        ]:
            (reports / name).write_text(json.dumps(obj), encoding="utf-8")

    def test_dominance_and_volume(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_fixture(root)
            out = r021.build_report(root)
            rows = {r["config"]: r for r in out["configs"]}
            self.assertIn("lexical_80", rows["retrieval_80"]["dominated_by"])
            self.assertEqual(
                rows["lexical_80"]["test_candidate_entries_upper_bound"], 800
            )
            self.assertFalse(
                out["summary"]["selected_depth10_640"][
                    "same_model_smaller_cap_sweep_available"
                ]
            )

    def test_candidate_semantics_mismatch_fails(self):
        one = {
            "entities": 1,
            "singleton_count": 0,
            "all_empty_baseline": 0.0,
            "candidate_pair_recall": 0.9,
            "candidate_entity_recall": 0.9,
            "all_matches_retrieved_rate": 0.9,
            "blocking_oracle_macro_f0_5": 0.9,
            "candidate_count_quantiles": {
                "p50": 1,
                "p90": 1,
                "p99": 1,
                "max": 1,
            },
        }
        two = {**one, "entities": 2}
        with self.assertRaises(ValueError):
            r021._assert_same_candidate_semantics({"x": one}, {"x": two})


if __name__ == "__main__":
    unittest.main()
