"""Regression guard for ID-independent RRF fusion ranks."""
from collections import defaultdict
from pathlib import Path
import unittest


def _ordinal_rrf(ids, base_scores, char_scores):
    weights = defaultdict(float)
    for scores, multiplier in ((base_scores, 1.0), (char_scores, 0.5)):
        ordered = sorted(scores, key=lambda key: (-scores[key], ids[key]))
        for rank, key in enumerate(ordered, 1):
            weights[key] += multiplier / (60 + rank)
    return dict(weights)


def _dense_rrf(base_scores, char_scores):
    weights = defaultdict(float)
    for scores, multiplier in ((base_scores, 1.0), (char_scores, 0.5)):
        rank_by_score = {
            score: rank
            for rank, score in enumerate(sorted(set(scores.values()), reverse=True), 1)
        }
        for key, score in scores.items():
            weights[key] += multiplier / (60 + rank_by_score[score])
    return dict(weights)


class RrfRankSemanticsTest(unittest.TestCase):
    def test_entity_id_permutation_changes_ordinal_but_not_dense_rrf(self):
        base = {"x": 1.0, "y": 1.0, "z": 1.0}
        char = {"y": 1.0, "z": 1.0}
        ids_a = {"x": "A", "y": "B", "z": "C"}
        ids_b = {"x": "C", "y": "A", "z": "B"}

        self.assertNotEqual(_ordinal_rrf(ids_a, base, char), _ordinal_rrf(ids_b, base, char))
        self.assertEqual(_dense_rrf(base, char), _dense_rrf(base, char))

    def test_production_rrf_weights_use_score_only_dense_rank(self):
        source = Path("src/ber/retrieval_v3.py").read_text(encoding="utf-8")
        self.assertIn(
            "1.0/(60+dense_rank() OVER(PARTITION BY anchor ORDER BY retrieval DESC)) weight",
            source,
        )
        self.assertIn(
            "0.5/(60+dense_rank() OVER(PARTITION BY anchor ORDER BY retrieval DESC)) weight",
            source,
        )
        self.assertNotIn(
            "60+row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC,r.entity_id)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
