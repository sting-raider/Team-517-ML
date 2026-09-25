import json
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
import numpy as np
from catboost import CatBoostClassifier
from ber.data import connect
from ber.features import features,FEATURE_NAMES
from ber.predict import predict
from ber.validate import validate


class ExportIntegrationTests(unittest.TestCase):
    def test_inference_resume_and_full_id_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            db=root/'tiny.duckdb'
            c=connect(db)
            c.execute('''CREATE TABLE test(entity_id VARCHAR,business_name VARCHAR,business_address VARCHAR,
                country VARCHAR,source INTEGER,n VARCHAR,a VARCHAR)''')
            records=[('S1-1','alpha','12 road','France',1,'alpha','12 road'),
                     ('S1-2','different','800 lane','India',1,'different','800 lane'),
                     ('S2-1','alpha','12 road','France',2,'alpha','12 road')]
            c.executemany('INSERT INTO test VALUES (?,?,?,?,?,?,?)',records)
            c.close()
            model_dir=root/'model'
            model_dir.mkdir()
            x=np.asarray([features('alpha','12 road','alpha','12 road',100,4,2),
                          features('alpha','12 road','other','90 lane',5,1,2)]*5,dtype=np.float32)
            model=CatBoostClassifier(iterations=2,depth=1,verbose=False,allow_writing_files=False,thread_count=1)
            model.fit(x,np.array([1,0]*5))
            model.save_model(str(model_dir/'mixed.cbm'))
            (model_dir/'model_config.json').write_text(json.dumps({'feature_names':FEATURE_NAMES,'threshold':.5,'candidate_cap':80}))
            out=root/'out'
            predict(db,model_dir,out,batch_size=1)
            before=(out/'matching_results.tsv').read_bytes()
            result=validate(db,out)
            self.assertEqual(result['anchors'],2)
            self.assertEqual(result['candidates'],1)
            self.assertIn('S1-2\t\n',before.decode())
            official=Path(__file__).resolve().parents[2]/'student_resource/utils/validate_submission.py'
            if official.exists():
                testdir=root/'test';testdir.mkdir()
                for source in (1,2,3):
                    with (testdir/f'test_source{source}.tsv').open('w',encoding='utf-8') as f:
                        f.write('entity_id\tbusiness_name\tbusiness_address\tcountry\n')
                        for record in records:
                            if record[4]==source:
                                f.write('\t'.join(record[:4])+'\n')
                checked=subprocess.run([sys.executable,str(official),'--matching',str(out/'matching_results.tsv'),
                    '--candidate',str(out/'candidate_pairs.tsv'),'--test-dir',str(testdir),'--check-ids'],capture_output=True,text=True)
                self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            predict(db,model_dir,out,batch_size=1)
            self.assertEqual(before,(out/'matching_results.tsv').read_bytes())
            (out/'candidate_pairs.tsv').write_text('source1_entity_id\tcandidate_entity_ids\nS1-1\tS2-1,S3-404\nS1-2\t\n')
            with self.assertRaisesRegex(ValueError,'nonexistent'):
                validate(db,out)


if __name__=='__main__':
    unittest.main()
