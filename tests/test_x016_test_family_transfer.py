import unittest
from collections import Counter

from tools.experiments import x016_test_family_transfer as m


class X016Tests(unittest.TestCase):
    def test_overlap_summary_distinguishes_cross_country(self):
        rows = [
            {"country": "India", "name": "alpha"},
            {"country": "US", "name": "alpha"},
            {"country": "US", "name": "beta"},
            {"country": "US", "name": ""},
        ]
        fit_name = Counter({"alpha": 2})
        fit_country = Counter({("India", "alpha"): 1})
        core_name = Counter({"alpha": 1})
        core_country = Counter({("India", "alpha"): 1})
        out = m.overlap_summary(
            rows,
            fit_name,
            fit_country,
            core_name,
            core_country,
        )
        self.assertEqual(out["anchors"], 4)
        self.assertEqual(out["nonempty_name_anchors"], 3)
        self.assertEqual(out["name_only_fit_family_overlap_anchors"], 2)
        self.assertEqual(out["same_country_fit_family_overlap_anchors"], 1)
        self.assertEqual(out["same_country_family_novel_anchors"], 2)

    def test_overlap_summary_expansion_increment(self):
        rows = [
            {"country": "US", "name": "a"},
            {"country": "US", "name": "b"},
            {"country": "US", "name": "c"},
        ]
        fit_name = Counter({"a": 1, "b": 1})
        fit_country = Counter({("US", "a"): 1, ("US", "b"): 1})
        core_name = Counter({"a": 1})
        core_country = Counter({("US", "a"): 1})
        out = m.overlap_summary(
            rows,
            fit_name,
            fit_country,
            core_name,
            core_country,
        )
        self.assertAlmostEqual(out["same_country_fit_family_overlap_rate"], 2 / 3)
        self.assertAlmostEqual(out["same_country_core_fit_family_overlap_rate"], 1 / 3)
        self.assertAlmostEqual(
            out["incremental_same_country_overlap_from_expanded_fit"],
            1 / 3,
        )


if __name__ == "__main__":
    unittest.main()
