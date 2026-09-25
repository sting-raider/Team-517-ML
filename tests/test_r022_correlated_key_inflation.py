import importlib.util
import math
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "experiments" / "r022_correlated_key_inflation.py"
spec = importlib.util.spec_from_file_location("r022", MODULE_PATH)
r022 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r022)


class R022AuditTests(unittest.TestCase):
    def test_current_formula_exact_address_contribution(self):
        expected = 40.0 + math.log(10_000_001.0 / 1000)
        self.assertAlmostEqual(r022.contribution("a:", 1000), expected)

    def test_four_word_address_emits_thirteen_scoring_hits(self):
        keys = r022.address_stack_keys(4, freq=1000, include_h=True)
        kinds = [kind for kind, _ in keys]
        self.assertEqual(len(keys), 13)
        self.assertEqual(kinds.count("a:"), 1)
        self.assertEqual(kinds.count("u:"), 4)
        self.assertEqual(kinds.count("v:"), 3)
        self.assertEqual(kinds.count("d:"), 4)
        self.assertEqual(kinds.count("h:"), 1)

    def test_one_word_address_stack_beats_four_rarest_name_words(self):
        address = r022.score_sum(r022.address_stack_keys(1, 1000, True))
        names = r022.score_sum([("w:", 1)] * 4)
        self.assertGreater(address, names)

    def test_family_max_removes_word_count_multiplication(self):
        one = r022.score_family_max(r022.address_stack_keys(1, 1000, True))
        four = r022.score_family_max(r022.address_stack_keys(4, 1000, True))
        self.assertAlmostEqual(one, four)
        self.assertLess(four, r022.score_sum(r022.address_stack_keys(4, 1000, True)))

    def test_invalid_frequency_fails_closed(self):
        with self.assertRaises(ValueError):
            r022.contribution("w:", 0)
        with self.assertRaises(ValueError):
            r022.contribution("w:", 1001)


if __name__ == "__main__":
    unittest.main()
