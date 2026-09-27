import unittest
from collections import Counter

from tools.experiments import i037_name_family_split_audit as m


class I037Tests(unittest.TestCase):
    def test_normalize_name(self):
        self.assertEqual(m.normalize_name("  Café—12 / SHOP!! "), "cafe 12 shop")
        self.assertEqual(m.normalize_name("ACME___Ltd."), "acme ltd")
        self.assertEqual(m.normalize_name(""), "")

    def test_fold_known_values(self):
        self.assertEqual(m.fold("S1-1"), "fit")
        self.assertEqual(m.fold("S1-3"), "holdout")
        self.assertEqual(m.fold("S1-925783039"), "calibrate")

    def test_sample_key_known_value(self):
        self.assertEqual(
            m.sample_key("S1-965667"),
            15486884846227462723892042835785360427,
        )

    def test_summarize_family_overlap(self):
        rows = [
            {"id": "a", "country": "India", "name": "alpha"},
            {"id": "b", "country": "India", "name": "beta"},
            {"id": "c", "country": "US", "name": "alpha"},
            {"id": "d", "country": "US", "name": ""},
        ]
        truth = {"a": 0, "b": 5, "c": 2, "d": 1}
        fit_name = Counter({"alpha": 3})
        fit_country = Counter({("India", "alpha"): 2, ("US", "gamma"): 1})
        core_name = Counter({"alpha": 1})
        core_country = Counter({("India", "alpha"): 1})
        out = m.summarize(
            rows,
            truth,
            fit_name,
            fit_country,
            core_name,
            core_country,
        )["all"]
        self.assertEqual(out["anchors"], 4)
        self.assertEqual(out["nonempty_name_anchors"], 3)
        self.assertEqual(out["name_family_seen_in_fit_anchors"], 2)
        self.assertEqual(out["same_country_name_family_seen_in_fit_anchors"], 1)
        self.assertEqual(out["family_novel_same_country_anchors"], 2)
        self.assertAlmostEqual(
            out["same_country_name_family_seen_in_fit_rate_nonempty"],
            1 / 3,
        )
        self.assertAlmostEqual(out["truth_composition"]["singleton_rate"], 1 / 4)
        self.assertAlmostEqual(
            out["truth_composition"]["high_cardinality_ge5_rate"],
            1 / 4,
        )


if __name__ == "__main__":
    unittest.main()
