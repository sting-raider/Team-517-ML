import unittest
import numpy as np
from ber.features import features
from ber.shortlist import shortlist_rows,shortlist_mask


class ShortlistTests(unittest.TestCase):
    def test_offline_and_production_candidates_agree(self):
        rows=[]
        for i in range(85):
            rows.append(('S1-1',f'S2-{i:03d}','alpha industries','12 main street',
                ('alpha industry '+str(i)) if i%3 else 'other business',
                ('12 main st '+str(i)) if i%4 else '',10.,2,2))
        x=np.asarray([features(*r[2:]) for r in rows],dtype=np.float32)
        targets=np.array([r[1] for r in rows])
        for cap in (10,20,30,40,60,80):
            keep=shortlist_mask(np.zeros(len(rows),dtype=int),targets,(x[:,0]+x[:,2])/2,
                (x[:,22]+x[:,24])/2,(x[:,42]>0)|(x[:,43]>0),cap)
            self.assertEqual(set(targets[keep]),{r[1] for r in shortlist_rows(rows,cap)})

    def test_small_groups_keep_every_candidate(self):
        keep=shortlist_mask(np.zeros(3,dtype=int),np.array(['a','b','c']),np.array([1.,.1,.2]),
            np.array([.3,.9,.7]),np.zeros(3,dtype=bool),20)
        self.assertTrue(keep.all())


if __name__=='__main__':
    unittest.main()
