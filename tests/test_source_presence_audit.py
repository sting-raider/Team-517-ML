import unittest

import numpy as np
import pandas as pd

from ber.source_presence_audit import build_labels, fold_bucket, norm_text


class D012Tests(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(norm_text("  Café—12/B  "), "cafe 12 b")
        self.assertEqual(norm_text("A_B+C"), "a b c")

    def test_fold_deterministic(self):
        self.assertEqual(fold_bucket("S1-123"), fold_bucket("S1-123"))
        self.assertTrue(0 <= fold_bucket("S1-123") < 100)

    def test_source_labels_align_by_id_not_row(self):
        s1 = pd.DataFrame({
            "entity_id": ["S1-2", "S1-1", "S1-3"],
            "business_name": ["b", "a", "c"],
            "business_address": ["y", "x", "z"],
            "country": ["US"] * 3,
        })
        gt = pd.DataFrame({
            "source1_entity_id": ["S1-1", "S1-3", "S1-2"],
            "matched_entity_ids": ["S2-1,S3-9", "", "S3-2"],
        })
        y = build_labels(s1, gt)
        np.testing.assert_array_equal(y["both_source"], [False, True, False])
        np.testing.assert_array_equal(y["s3_only"], [True, False, False])
        np.testing.assert_array_equal(y["s2_only"], [False, False, False])


if __name__ == "__main__":
    unittest.main()
