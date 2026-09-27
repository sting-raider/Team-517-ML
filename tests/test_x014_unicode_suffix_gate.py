import collections
import importlib.util
import pathlib
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "experiments" / "x014_unicode_suffix_gate.py"
SPEC = importlib.util.spec_from_file_location("x014", SCRIPT)
x014 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(x014)


class X014Tests(unittest.TestCase):
    def test_normalization_decomposes_accents(self):
        self.assertEqual(x014.norm_folded("Société Démo, LLC."), "societe demo llc")
        self.assertEqual(x014.norm_unicode("Société Démo, LLC."), "société démo llc")
        self.assertEqual(x014.strip_suffix("société démo llc"), ("société démo", "llc"))

    def test_address_word_contract(self):
        self.assertEqual(
            x014.address_words(x014.norm_folded("Unit 11, 2621 Côté Road near The Mall")),
            {"cote", "mall"},
        )
        self.assertEqual(
            x014.address_words(x014.norm_unicode("Unit 11, 2621 Côté Road near The Mall")),
            {"côté", "mall"},
        )

    def test_rare_word_cutoff_and_tie(self):
        df = collections.Counter({"alpha": 4, "béta": 4, "gamma": 1001})
        self.assertEqual(x014.select_rare("alpha\x1ebéta\x1egamma", df), ("alpha", 4))
        self.assertEqual(
            x014.select_rare("gamma", collections.Counter({"gamma": 1001})),
            ("", 1001),
        )

    def test_transition_counts(self):
        self.assertEqual(
            x014.transition(bytearray([0, 1, 2, 2]), bytearray([1, 1, 1, 2])),
            {"0->1": 1, "1->1": 1, "2->1": 1, "2->2": 1},
        )

    def test_small_end_to_end_view(self):
        rows = [
            ["France", "cafe demo llc", "café demo llc", "cafe demo", "café demo", "1", "paris", "paris"],
            ["France", "cafe demo", "cafe demo", "cafe demo", "cafe demo", "0", "paris", "paris"],
            ["US", "acme llc", "acme llc", "acme", "acme", "1", "tyler", "tyler"],
        ]
        with tempfile.TemporaryDirectory() as td:
            spool = pathlib.Path(td) / "s.tsv"
            with spool.open("w", encoding="utf-8", newline="") as f:
                import csv
                csv.writer(f, delimiter="\t", lineterminator="\n").writerows(rows)
            df = {
                "France": collections.Counter({"paris": 2}),
                "US": collections.Counter({"tyler": 1}),
            }
            suffix = collections.Counter({"France": 1, "US": 1})
            folded, _ = x014.audit_view(spool, "folded", "folded", df, df, suffix)
            unicode_view, _ = x014.audit_view(spool, "unicode", "folded", df, df, suffix)
            self.assertEqual(folded["France"]["cross_original_collision_rows"], 1)
            self.assertEqual(unicode_view["France"]["cross_original_collision_rows"], 0)
            self.assertEqual(folded["US"]["cross_original_collision_rows"], 0)
            self.assertEqual(unicode_view["US"]["cross_original_collision_rows"], 0)


if __name__ == "__main__":
    unittest.main()
