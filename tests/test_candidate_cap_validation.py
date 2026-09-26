import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ber.validate import validate


class FakeConnection:
    def __init__(self,anchors):
        self.anchors=[(anchor,) for anchor in anchors]
        self.returned=False

    def execute(self,*args,**kwargs):
        return self

    def fetchmany(self,size):
        if self.returned:
            return []
        self.returned=True
        return self.anchors

    def close(self):
        pass


def write_outputs(folder,matching,candidates):
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'matching_results.tsv').write_text(
        'source1_entity_id\\tmatched_entity_ids\\n'+matching,encoding='utf-8')
    (folder/'candidate_pairs.tsv').write_text(
        'source1_entity_id\\tcandidate_entity_ids\\n'+candidates,encoding='utf-8')


class CandidateCapValidationTests(unittest.TestCase):
    def run_validate(self,matching,candidates,cap):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            write_outputs(out,matching,candidates)
            fake=FakeConnection(['S1-1'])
            with patch('ber.validate.connect',return_value=fake):
                return validate(Path('unused.duckdb'),out,check_ids=False,
                                max_candidates_per_anchor=cap)

    def test_exact_cap_passes_and_reports_observed_max(self):
        result=self.run_validate('S1-1\\tS2-1\\n','S1-1\\tS2-1,S3-1\\n',2)
        self.assertEqual(result['max_candidates_observed'],2)
        self.assertEqual(result['max_candidates_allowed'],2)

    def test_cap_plus_one_fails_loud(self):
        with self.assertRaisesRegex(ValueError,r'Candidate cap exceeded under S1-1: 2 > 1'):
            self.run_validate('S1-1\\tS2-1\\n','S1-1\\tS2-1,S3-1\\n',1)

    def test_duplicate_semantics_still_fail_before_counting(self):
        with self.assertRaisesRegex(ValueError,r'Duplicate target IDs under S1-1'):
            self.run_validate('S1-1\\t\\n','S1-1\\tS2-1,S2-1\\n',1)

    def test_empty_candidates_pass(self):
        result=self.run_validate('S1-1\\t\\n','S1-1\\t\\n',1)
        self.assertEqual(result['max_candidates_observed'],0)

    def test_omitted_cap_preserves_legacy_behavior(self):
        result=self.run_validate('S1-1\\tS2-1\\n','S1-1\\tS2-1,S3-1\\n',None)
        self.assertEqual(result['max_candidates_observed'],2)
        self.assertIsNone(result['max_candidates_allowed'])

    def test_nonpositive_cap_is_rejected(self):
        with self.assertRaisesRegex(ValueError,r'must be at least 1'):
            self.run_validate('S1-1\\t\\n','S1-1\\t\\n',0)


if __name__=='__main__':
    unittest.main()
