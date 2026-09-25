import unittest
from pathlib import Path
from ber.benchmark import (
    anchor_fold, candidate_count_stats, filter_mapping, filter_targets, retrieval_metrics, run
)


class BenchmarkHelperTests(unittest.TestCase):
    def test_fold_is_deterministic_and_known(self):
        expected = {
            'S1-1': 'fit',
            'S1-2': 'fit',
            'S1-3': 'holdout',
            'S1-4': 'calibrate',
            'S1-5': 'fit',
            'S1-6': 'fit',
            'S1-7': 'fit',
            'S1-8': 'fit',
        }
        self.assertEqual({k: anchor_fold(k) for k in expected}, expected)

    def test_candidate_count_stats_include_mean_and_tail(self):
        truth = {'a': {'x'}, 'b': set(), 'c': {'y'}}
        candidates = {'a': {'x', 'z'}, 'b': set(), 'c': {'q'}}
        stats = candidate_count_stats(truth, candidates)
        self.assertEqual(stats['total'], 3)
        self.assertEqual(stats['mean'], 1.0)
        self.assertEqual(stats['p50'], 1.0)
        self.assertEqual(stats['max'], 2.0)

    def test_country_and_source_filters_do_not_mutate_inputs(self):
        mapping = {'a': {'s2', 's3'}, 'b': {'s3'}}
        by_source = {'s2': 2, 's3': 3}
        self.assertEqual(filter_mapping(mapping, ['b']), {'b': {'s3'}})
        self.assertEqual(filter_targets(mapping, by_source, 2), {'a': {'s2'}, 'b': set()})
        self.assertEqual(mapping['a'], {'s2', 's3'})

    def test_retrieval_metrics_use_official_oracle(self):
        truth = {'a': set(), 'b': {'x', 'y'}}
        candidates = {'a': {'noise'}, 'b': {'x'}}
        report = retrieval_metrics(truth, candidates)
        self.assertEqual(report['candidate_pair_recall'], .5)
        self.assertAlmostEqual(report['blocking_oracle_macro_f0_5'], (1 + 1.25 / 1.5) / 2)
        self.assertEqual(report['candidate_counts']['total'], 2)

    def test_holdout_requires_explicit_override_before_io(self):
        with self.assertRaisesRegex(ValueError, 'guarded'):
            run(Path('/does/not/exist.duckdb'), Path('/tmp/nope.json'), fold='holdout')


if __name__ == '__main__':
    unittest.main()
