import math
import unittest

from ber.idf import (
    IDF_FEATURE_NAMES,
    IDF_VERSION,
    idf_weight,
    pair_token_weight,
    table_names,
    weighted_overlap,
)
from ber.v3 import V3_NAMES
from ber.v5 import V5_NAMES, pair_query


class TestIdfFeatures(unittest.TestCase):
    def test_schema_is_v3_plus_eight(self):
        self.assertEqual(len(IDF_FEATURE_NAMES), 8)
        self.assertEqual(V5_NAMES[: len(V3_NAMES)], V3_NAMES)
        self.assertEqual(V5_NAMES[len(V3_NAMES):], IDF_FEATURE_NAMES)
        self.assertEqual(len(V5_NAMES), len(V3_NAMES) + 8)
        sql = pair_query("train", "anchors", "pairs")
        self.assertIn("m001_idf_profile_train", sql)
        self.assertIn("right_source", sql)
        self.assertIn("ldf.source=1", sql)
        self.assertIn("rdf.source=j.right_source", sql)

    def test_idf_positive_and_monotone(self):
        self.assertGreater(idf_weight(1000, 1), idf_weight(1000, 900))
        self.assertGreater(idf_weight(1000, 900), 0.0)
        with self.assertRaises(ValueError):
            idf_weight(10, 11)

    def test_pair_weight_is_symmetric_and_source_local(self):
        a = pair_token_weight(1000, 2, 500, 200)
        b = pair_token_weight(500, 200, 1000, 2)
        self.assertAlmostEqual(a, b, places=12)
        self.assertGreater(a, pair_token_weight(1000, 800, 500, 400))

    def test_weighted_overlap_exact_empty_and_directional(self):
        weights = {"rare": 6.0, "common": 1.0, "shared": 2.0}
        self.assertEqual(weighted_overlap(set(), set(), {}), (0.0, 0.0, 0.0, 0.0))
        self.assertEqual(weighted_overlap({"rare"}, {"rare"}, weights), (1.0, 1.0, 1.0, 1.0))
        lr = weighted_overlap({"rare", "shared"}, {"shared", "common"}, weights)
        rl = weighted_overlap({"shared", "common"}, {"rare", "shared"}, weights)
        self.assertAlmostEqual(lr[0], rl[0], places=12)
        self.assertAlmostEqual(lr[1], rl[1], places=12)
        self.assertAlmostEqual(lr[2], rl[3], places=12)
        self.assertAlmostEqual(lr[3], rl[2], places=12)
        for value in lr:
            self.assertTrue(math.isfinite(value))
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_rare_mismatch_reduces_similarity_more(self):
        weights = {"rare": 7.0, "common": 1.0, "shared": 2.0}
        original = {"rare", "common", "shared"}
        rare_missing = {"common", "shared"}
        common_missing = {"rare", "shared"}
        self.assertLess(
            weighted_overlap(original, rare_missing, weights)[0],
            weighted_overlap(original, common_missing, weights)[0],
        )

    def test_table_names_fail_closed_on_sql_identifier(self):
        self.assertEqual(
            table_names("train"),
            ("m001_idf_profile_train", "m001_idf_token_train", "m001_idf_meta_train"),
        )
        with self.assertRaises(ValueError):
            table_names("train;drop table train")
        self.assertEqual(IDF_VERSION, 1)


if __name__ == "__main__":
    unittest.main()
