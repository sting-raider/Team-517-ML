import unittest
from ber.metrics import row_score, evaluate


class OfficialMetricTests(unittest.TestCase):
    def test_published_example(self):
        self.assertAlmostEqual(row_score({'a','b'}, {'a','b','c'}), 5/7)

    def test_singletons_and_no_predictions(self):
        self.assertEqual(row_score([], []), 1)
        self.assertEqual(row_score([], ['x']), 0)
        self.assertEqual(row_score(['x'], []), 0)

    def test_macro_not_pair_weighted(self):
        report = evaluate({'a': [], 'b': list(range(100))}, {'a': [], 'b': []})
        self.assertEqual(report['macro_f0_5'], .5)

    def test_blocker_oracle(self):
        report = evaluate({'a': [], 'b': ['x','y']}, {}, {'a':['z'], 'b':['x','bad']})
        self.assertEqual(report['candidate_pair_recall'], .5)
        self.assertAlmostEqual(report['blocking_oracle_macro_f0_5'], (1+1.25/1.5)/2)


if __name__ == '__main__':
    unittest.main()
