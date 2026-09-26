import unittest

from ber.features import (
    CHAR_NGRAM_FEATURE_NAMES,
    FEATURE_NAMES,
    batch_char_ngram_features,
    char_ngram_features,
)


class CharNgramFeatureTests(unittest.TestCase):
    def test_legacy_schema_is_unchanged(self):
        self.assertEqual(len(FEATURE_NAMES),47)
        self.assertEqual(FEATURE_NAMES[-3:],['retrieval','key_hits','source'])
        self.assertEqual(len(CHAR_NGRAM_FEATURE_NAMES),8)
        self.assertTrue(set(FEATURE_NAMES).isdisjoint(CHAR_NGRAM_FEATURE_NAMES))

    def test_exact_and_spacing_equivalent_pairs(self):
        exact=char_ngram_features('acme private limited','12 main road',
                                  'acme private limited','12 main road')
        spaced=char_ngram_features('acme pvt ltd','12 main road',
                                   'acmepvtltd','12mainroad')
        self.assertEqual(exact,[1.0]*8)
        self.assertEqual(spaced,[1.0]*8)

    def test_containment_is_distinct_from_jaccard(self):
        values=char_ngram_features('acme technologies private limited','',
                                   'acme technologies','')
        self.assertLess(values[0],1.0)
        self.assertEqual(values[1],1.0)
        self.assertLess(values[2],1.0)
        self.assertEqual(values[3],1.0)
        self.assertEqual(values[4:],[0.0]*4)

    def test_missing_and_too_short_text_is_neutral(self):
        self.assertEqual(char_ngram_features('','','acme',''),[0.0]*8)
        self.assertEqual(char_ngram_features('ab','','ab',''),[0.0]*8)

    def test_batch_shape_and_determinism(self):
        rows=[
            ('acme pvt ltd','12 main road','acmepvtltd','12mainroad',1.0,2,2),
            ('alpha foods','','omega motors','',0.5,1,3),
        ]
        first=batch_char_ngram_features(rows)
        second=batch_char_ngram_features(rows)
        self.assertEqual(first.shape,(2,8))
        self.assertEqual(first.dtype.name,'float32')
        self.assertTrue((first==second).all())
        self.assertTrue(((0<=first)&(first<=1)).all())


if __name__=='__main__':
    unittest.main()
