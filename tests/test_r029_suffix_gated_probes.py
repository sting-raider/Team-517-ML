import collections
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "experiments" / "r029_suffix_gated_probes.py"
SPEC = importlib.util.spec_from_file_location("r029", SCRIPT)
r029 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r029)


class R029Tests(unittest.TestCase):
    def test_normalize_and_suffix(self):
        self.assertEqual(r029.repo_norm("Société Démo, LLC."), "societe demo llc")
        self.assertEqual(r029.strip_suffix("acme private limited"), ("acme", "private limited"))
        self.assertEqual(r029.strip_suffix("limited"), ("limited", ""))

    def test_address_words_match_f007a_contract(self):
        a = r029.repo_norm("Unit 11, 2621 Cotton Road near The Mall")
        self.assertEqual(r029.address_words_from_norm(a), {"cotton", "mall"})
        self.assertEqual(r029.first_number(a), "11")

    def test_rare_word_cutoff_and_tie(self):
        df = collections.Counter({"alpha": 4, "beta": 4, "gamma": 1001})
        self.assertEqual(r029.choose_rare_word("beta alpha gamma", df), ("alpha", 4))
        df = collections.Counter({"alpha": 1001, "beta": 2000})
        self.assertEqual(r029.choose_rare_word("alpha beta", df), ("", 1001))

    def test_group_collision_metrics(self):
        groups = {}
        r029.add_group(groups, "acme", "acme llc", True)
        r029.add_group(groups, "acme", "acme llc", True)
        r029.add_group(groups, "acme", "acme inc", True)
        out = r029.summarize_groups(
            groups,
            collections.Counter({"acme llc": 2, "acme inc": 1}),
            3,
            collections.Counter(),
        )
        self.assertEqual(out["covered_query_rows"], 3)
        self.assertEqual(out["cross_original_collision_query_rows"], 3)
        self.assertAlmostEqual(out["cross_original_collision_rate"], 1.0)
        self.assertEqual(out["group_size"]["p50"], 3)
        self.assertEqual(out["cross_original_fanout"]["max"], 2)

    def test_unaffected_row_still_contributes_posting_collision(self):
        groups = {}
        r029.add_group(groups, "acme", "acme llc", True)
        r029.add_group(groups, "acme", "acme", False)
        out = r029.summarize_groups(
            groups,
            collections.Counter({"acme llc": 1, "acme": 1}),
            1,
            collections.Counter(),
        )
        self.assertEqual(out["covered_query_rows"], 1)
        self.assertEqual(out["cross_original_collision_query_rows"], 1)
        self.assertEqual(out["cross_original_fanout"]["max"], 1)

    def test_spooled_composite_key(self):
        df = collections.Counter({"alpha": 2, "beta": 8})
        key, d = r029.make_key_spooled(
            "number_rare_word", "acme", "42", "alpha\x1ebeta", df
        )
        self.assertEqual(key, "acme\x1f42\x1falpha")
        self.assertEqual(d, 2)


if __name__ == "__main__":
    unittest.main()
