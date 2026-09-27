import unittest

from tools.experiments.r030_adaptive_address_probes import (
    address_words,
    hist_quantile,
    normalize,
    select_policy,
)
from collections import Counter


class R030AdaptiveAddressProbeTests(unittest.TestCase):
    def test_unicode_and_stopword_semantics(self):
        self.assertEqual(normalize("Rúe de l'Église"), "rue de l eglise")
        self.assertEqual(
            address_words("12 Rúe de l'Église, Floor 2"),
            {"rue", "eglise"},
        )

    def test_fixed_policies(self):
        eligible = [(i, str(i)) for i in range(1, 10)]
        self.assertEqual(len(select_policy(eligible, "fixed4")), 4)
        self.assertEqual(len(select_policy(eligible, "fixed6")), 6)
        self.assertEqual(len(select_policy(eligible, "fixed8")), 8)

    def test_adaptive_budget_is_bounded(self):
        eligible = [(1, "a"), (2, "b"), (3, "c"), (4, "d"),
                    (50, "e"), (100, "f"), (101, "g"), (200, "h")]
        selected = select_policy(eligible, "adaptive4to8_budget200")
        self.assertEqual([x[1] for x in selected], ["a", "b", "c", "d", "e", "f"])
        self.assertLessEqual(sum(df for df, _ in selected[4:]), 200)
        self.assertLessEqual(len(selected), 8)

    def test_hist_quantile(self):
        hist = Counter({0: 2, 1: 3, 7: 5})
        self.assertEqual(hist_quantile(hist, 0.5), 1)
        self.assertEqual(hist_quantile(hist, 0.9), 7)


if __name__ == "__main__":
    unittest.main()
