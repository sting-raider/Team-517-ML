import csv
import tempfile
import unittest
from pathlib import Path
import importlib.util

MODULE = Path(__file__).parents[1] / "tools" / "experiments" / "x015_neural_cardinality_drift.py"
spec = importlib.util.spec_from_file_location("x015", MODULE)
x015 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x015)


def write_tsv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


class X015Tests(unittest.TestCase):
    def test_population_and_transfer_arithmetic(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_tsv(
                d / "train.tsv",
                ["entity_id", "business_name", "business_address", "country"],
                [
                    ["a", "A", "", "US"],
                    ["b", "B", "", "US"],
                    ["c", "C", "", "India"],
                    ["d1", "D", "", "India"],
                ],
            )
            write_tsv(
                d / "truth.tsv",
                ["source1_entity_id", "matched_entity_ids"],
                [["a", ""], ["b", "x,y"], ["c", "z"], ["d1", "u,v,w"]],
            )
            write_tsv(
                d / "test.tsv",
                ["entity_id", "business_name", "business_address", "country"],
                [["u1", "", "", "US"], ["i1", "", "", "India"], ["f1", "", "", "France"]],
            )
            pop = x015.scan_population(d / "train.tsv", d / "truth.tsv", d / "test.tsv")
            self.assertEqual(pop["train"]["entities"], 4)
            self.assertEqual(pop["train"]["truth_edges"], 6)
            self.assertEqual(pop["train"]["singletons"], 1)
            self.assertAlmostEqual(
                pop["train"]["countries"]["US"]["mean_truth_cardinality"], 1.0
            )
            self.assertAlmostEqual(
                pop["train"]["countries"]["India"]["mean_truth_cardinality"], 2.0
            )

    def test_duplicate_source1_fails(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_tsv(d / "train.tsv", ["entity_id", "country"], [["a", "US"], ["a", "US"]])
            write_tsv(
                d / "truth.tsv",
                ["source1_entity_id", "matched_entity_ids"],
                [["a", ""]],
            )
            write_tsv(d / "test.tsv", ["entity_id", "country"], [["x", "US"]])
            with self.assertRaisesRegex(ValueError, "duplicate Source-1"):
                x015.scan_population(d / "train.tsv", d / "truth.tsv", d / "test.tsv")

    def test_v6_addition_sum_guard(self):
        population = {
            "test_source1": {
                "entities": 3,
                "countries": {"US": 1, "India": 1, "France": 1},
            },
            "train": {
                "countries": {
                    "US": {"mean_truth_cardinality": 1, "singleton_rate": 0},
                    "India": {"mean_truth_cardinality": 1, "singleton_rate": 0},
                }
            },
        }
        v3 = {
            "countries": {
                "US": {"entities": 1, "new_matches": 0, "new_empty": 1},
                "India": {"entities": 1, "new_matches": 0, "new_empty": 1},
                "France": {
                    "entities": 1,
                    "new_matches": 5_819_438,
                    "new_empty": 102_596,
                },
            }
        }
        v5 = {
            "completion": {
                "validation": {"anchors": 3, "matches": 1, "empty_predictions": 1}
            }
        }
        france = {"v5_neural32": {"predicted_edges": 0, "empty_predictions": 0}}
        v6 = {
            "rows": 3,
            "added_by_country": {"US": 1, "India": 0, "France": 0},
            "total_added": 2,
        }
        with self.assertRaisesRegex(ValueError, "do not sum"):
            x015.derive_transfer(population, v3, v5, france, v6)

    def test_committed_aggregate_derivation(self):
        population = {
            "test_source1": {
                "entities": 1_732_544,
                "countries": {"US": 663_106, "India": 809_986, "France": 259_452},
            },
            "train": {
                "countries": {
                    "US": {
                        "mean_truth_cardinality": 3.4590570044717834,
                        "singleton_rate": 0.055828163849042746,
                    },
                    "India": {
                        "mean_truth_cardinality": 3.4645432229604567,
                        "singleton_rate": 0.05587825015738439,
                    },
                }
            },
        }
        v3 = {
            "countries": {
                "US": {"entities": 663_106, "new_matches": 2_193_422, "new_empty": 38_185},
                "India": {
                    "entities": 809_986,
                    "new_matches": 2_495_140,
                    "new_empty": 55_498,
                },
                "France": {
                    "entities": 259_452,
                    "new_matches": 1_130_876,
                    "new_empty": 8_915,
                },
            }
        }
        v5 = {
            "completion": {
                "validation": {
                    "anchors": 1_732_544,
                    "matches": 5_743_094,
                    "empty_predictions": 99_424,
                }
            }
        }
        france = {
            "v5_neural32": {"predicted_edges": 931_003, "empty_predictions": 11_980}
        }
        v6 = {
            "rows": 1_732_544,
            "added_by_country": {"US": 11_274, "India": 8_071, "France": 5_798},
            "total_added": 25_143,
        }
        out = x015.derive_transfer(population, v3, v5, france, v6)
        self.assertEqual(out["seen_countries_US_India"]["v5"]["matches"], 4_812_091)
        self.assertEqual(
            out["seen_countries_US_India"]["v5"]["empty_predictions"], 87_444
        )
        self.assertEqual(out["france_unlabeled"]["v6"]["matches"], 936_801)
        self.assertAlmostEqual(
            out["france_unlabeled"]["v5"]["mean_matches"], 3.5883438940536205
        )


if __name__ == "__main__":
    unittest.main()
