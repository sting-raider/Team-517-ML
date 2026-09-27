import inspect
import math
import unittest

from ber import retrieval_v3


class RecordingConnection:
    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append(str(sql))
        return self


class SourceCharacterFrequencyTests(unittest.TestCase):
    def test_source_char_index_scopes_frequency_by_target_source(self):
        c = RecordingConnection()
        retrieval_v3.build_source_char_index(c, "train")
        sql = "\n".join(c.statements)
        self.assertIn("hash(country,source,k)", sql)
        self.assertIn("train_source_char_freq", sql)
        self.assertIn("freq<=2000", sql)
        self.assertNotIn("hash(country,k) AS key", sql)

    def test_query_keeps_six_unique_grams_per_family_not_six_per_source(self):
        c = RecordingConnection()
        retrieval_v3.source_char_candidates(c, "train", "anchors", "out", 64)
        query_sql = c.statements[0]
        self.assertIn("CROSS JOIN (VALUES(2),(3))", query_sql)
        self.assertIn("GROUP BY anchor,k,kind", query_sql)
        self.assertIn("PARTITION BY anchor,kind ORDER BY best_freq,k", query_sql)
        self.assertNotIn("PARTITION BY anchor,s.source,kind", query_sql)

    def test_pooled_cutoff_can_hide_source_rare_character_evidence(self):
        cutoff = 2000
        # Common in S2, unique in S3: pooled INT003 drops the gram everywhere.
        s2, s3 = 2001, 1
        self.assertGreater(s2 + s3, cutoff)
        self.assertGreater(s2, cutoff)
        self.assertLessEqual(s3, cutoff)

        # Both individually eligible, but their pooled frequency crosses the cutoff.
        s2, s3 = 1500, 600
        self.assertGreater(s2 + s3, cutoff)
        self.assertLessEqual(s2, cutoff)
        self.assertLessEqual(s3, cutoff)

    def test_source_local_weight_never_dilutes_an_eligible_source(self):
        corpus = 10_000_001.0
        cases = [(1, 1999), (7, 13), (400, 300), (1500, 600)]
        for s2, s3 in cases:
            pooled = s2 + s3
            for local in (s2, s3):
                self.assertGreaterEqual(
                    math.log(corpus / local),
                    math.log(corpus / pooled),
                )

    def test_selected_int003_fusion_remains_on_pooled_character_path(self):
        source = inspect.getsource(retrieval_v3.fused_candidates)
        self.assertIn("char_candidates(", source)
        self.assertIn("'fusion_character'", source)
        self.assertNotIn("source_char_candidates(", source)


if __name__ == "__main__":
    unittest.main()
