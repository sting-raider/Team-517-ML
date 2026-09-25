import math
import unittest
import tempfile
from pathlib import Path

import duckdb

from ber.blocking import build_index, candidates
from ber.features import FEATURE_NAMES
from ber.predict import prepare_groups
from ber.provenance import PROVENANCE_FEATURE_NAMES, provenance_values


class CandidateProvenanceTests(unittest.TestCase):
    def make_db(self):
        tempdir=tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        c=duckdb.connect(str(Path(tempdir.name)/'m002.duckdb'))
        self.addCleanup(c.close)
        c.execute('''CREATE TABLE train(
            entity_id VARCHAR, business_name VARCHAR, business_address VARCHAR,
            country VARCHAR, source INTEGER, n VARCHAR, a VARCHAR
        )''')
        c.executemany('INSERT INTO train VALUES (?,?,?,?,?,?,?)', [
            ('A1','Alpha Cafe','12 Main Street','US',1,'alpha cafe','12 main street'),
            ('T0','Alpha Cafe','12 Main Street','US',3,'alpha cafe','12 main street'),
            ('T1','Alpha Cafe','12 Main Street','US',2,'alpha cafe','12 main street'),
            ('T2','Alpha Cafe Annex','12 Main Avenue','US',2,'alpha cafe annex','12 main avenue'),
            ('T3','Beta Shop','99 Side Road','US',3,'beta shop','99 side road'),
        ])
        build_index(c,'train')
        c.execute("CREATE TABLE anchors AS SELECT * FROM train WHERE source=1")
        return c

    def test_provenance_preserves_legacy_candidates_and_scores(self):
        c=self.make_db()
        candidates(c,'train','anchors','legacy',cap=10)
        candidates(c,'train','anchors','prov',cap=10,provenance=True)
        legacy=c.execute('SELECT anchor,rid,retrieval,hits FROM legacy ORDER BY anchor,rid').fetchall()
        prov=c.execute('SELECT anchor,rid,retrieval,hits FROM prov ORDER BY anchor,rid').fetchall()
        self.assertEqual(len(legacy),len(prov))
        for left,right in zip(legacy,prov):
            self.assertEqual(left[:2],right[:2])
            self.assertAlmostEqual(left[2],right[2],places=6)
            self.assertEqual(left[3],right[3])

    def test_hit_families_partition_key_hits_and_rank_is_id_independent(self):
        c=self.make_db()
        candidates(c,'train','anchors','prov',cap=10,provenance=True)
        rows=c.execute('''SELECT p.hits,p.name_exact_hits,p.address_exact_hits,p.name_token_hits,
            p.address_token_hits,p.address_bigram_hits,p.name_number_hits,p.address_number_hits,
            p.min_key_freq,p.candidate_rank,t.entity_id,p.retrieval
            FROM prov p JOIN train t ON p.rid=t.rowid ORDER BY p.retrieval DESC,t.entity_id''').fetchall()
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r[0],sum(r[1:8]))
            self.assertGreaterEqual(r[8],1)
        scores=sorted({r[11] for r in rows},reverse=True)
        expected_rank={score:i+1 for i,score in enumerate(scores)}
        for r in rows:
            self.assertEqual(r[9],expected_rank[r[11]])
        exact_ties=[r for r in rows if r[10] in ('T0','T1')]
        self.assertEqual(len(exact_ties),2)
        self.assertEqual(len({r[9] for r in exact_ties}),1)
        self.assertEqual(len({r[11] for r in exact_ties}),1)

    def test_cap_uses_same_top_candidate(self):
        c=self.make_db()
        candidates(c,'train','anchors','legacy',cap=1)
        candidates(c,'train','anchors','prov',cap=1,provenance=True)
        self.assertEqual(c.execute('SELECT rid FROM legacy').fetchone()[0],
                         c.execute('SELECT rid FROM prov').fetchone()[0])

    def test_inference_feature_batch_appends_provenance_without_reordering_base(self):
        base_row=('A1','T1','alpha cafe','12 main street','alpha cafe','12 main street',10.0,2,2)
        prov=(1,1,1,0,0,0,0,0,1)
        records,x=prepare_groups(([[base_row+prov]],None,True))
        self.assertEqual(records,[('A1','T1')])
        self.assertEqual(x.shape,(1,len(FEATURE_NAMES)+len(PROVENANCE_FEATURE_NAMES)))
        self.assertEqual(float(x[0,len(FEATURE_NAMES)]),1.0)
        legacy_records,legacy_x=prepare_groups(([[base_row]],None,False))
        self.assertEqual(legacy_records,records)
        self.assertEqual(legacy_x.shape,(1,len(FEATURE_NAMES)))

    def test_provenance_vector_schema_and_validation(self):
        values=provenance_values(2,1,0,2,1,0,1,1,7)
        self.assertEqual(len(values),len(PROVENANCE_FEATURE_NAMES))
        self.assertEqual(values[0],2.0)
        self.assertAlmostEqual(values[-1],math.log1p(7))
        with self.assertRaises(ValueError):
            provenance_values(0,1,0,0,0,0,0,0,1)
        with self.assertRaises(ValueError):
            provenance_values(1,-1,0,0,0,0,0,0,1)


if __name__=='__main__':
    unittest.main()
