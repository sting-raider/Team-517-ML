import math
import unittest
from ber.features import features,FEATURE_NAMES


class FeatureTests(unittest.TestCase):
    def test_empty_fields_are_finite(self):
        v=features('','','','',0,0,2)
        self.assertEqual(len(v),len(FEATURE_NAMES))
        self.assertTrue(all(math.isfinite(x) for x in v))
        self.assertEqual(v[FEATURE_NAMES.index('name_exact')],0)

    def test_address_number_conflict_is_preserved(self):
        v=features('alpha','12 main st','alpha','27 main st',1,1,3)
        self.assertEqual(v[FEATURE_NAMES.index('address_number_conflict')],1)
        self.assertEqual(v[FEATURE_NAMES.index('name_exact')],1)


if __name__=='__main__':
    unittest.main()
