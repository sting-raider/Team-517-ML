import unittest
from tools.experiments.d020_int006_selection_stability import ranks, spearman_no_ties

class D020Tests(unittest.TestCase):
    def test_rank(self):
        rows=[{"name":"a","x":.8},{"name":"b","x":.9},{"name":"c","x":.7}]
        self.assertEqual(ranks(rows,"x"),{"b":1,"a":2,"c":3})
    def test_spearman_identical(self):
        r={"a":1,"b":2,"c":3}
        self.assertEqual(spearman_no_ties(r,r),1.0)
    def test_spearman_one_adjacent_swap(self):
        self.assertAlmostEqual(
            spearman_no_ties({"a":1,"b":2,"c":3,"d":4,"e":5},
                              {"a":2,"b":1,"c":3,"d":4,"e":5}),0.9)
if __name__=="__main__":
    unittest.main()
