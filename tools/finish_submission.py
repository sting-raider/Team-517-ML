"""Resume the first full export, then validate its exact submission format."""
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ['BER_FAST_FEATURES']='1'
from ber.predict import predict,sha256
from ber.validate import validate


def main():
    os.chdir(ROOT)
    out=ROOT/'output/submission_v1'
    status=out/'completion.json'
    started=time.time()
    status.write_text(json.dumps({'status':'RUNNING','started_epoch':started}),encoding='utf-8')
    try:
        predict(ROOT/'artifacts/data.duckdb',ROOT/'artifacts/submission_v1',out,
                batch_size=10000,workers=4,query_batches=1)
        local=validate(ROOT/'artifacts/data.duckdb',out,check_ids=False)
        command=[sys.executable,str(ROOT.parent/'student_resource/utils/validate_submission.py'),
                 '--matching',str(out/'matching_results.tsv'),
                 '--test-dir',str(ROOT.parent/'student_resource/dataset/test')]
        official=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        (out/'official_validation.txt').write_text(official.stdout+'\n'+official.stderr,encoding='utf-8')
        if official.returncode:
            raise RuntimeError(f'Official validator returned {official.returncode}; see official_validation.txt')
        result={'status':'PASS','started_epoch':started,'finished_epoch':time.time(),
                'streaming_validation':local,
                'streaming_validation_scope':'matching_results.tsv + candidate_pairs.tsv; target-ID existence skipped',
                'official_validation_exit_code':official.returncode,
                'official_validation_scope':'matching_results.tsv only; candidate_pairs.tsv is checked by ber.validate to avoid the official validator full-candidate memory cost',
                'matching_sha256':sha256(out/'matching_results.tsv'),
                'candidate_sha256':sha256(out/'candidate_pairs.tsv')}
        status.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)
    except BaseException as error:
        status.write_text(json.dumps({'status':'FAILED','error':repr(error),
            'traceback':traceback.format_exc()},indent=2),encoding='utf-8')
        raise


if __name__=='__main__':
    main()
