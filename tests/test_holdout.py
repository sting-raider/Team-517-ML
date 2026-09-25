import json
import tempfile
import unittest
from pathlib import Path

from ber.holdout import authorize_confirmation, load_freeze, register_consumption


FREEZE = {
    'version': 1,
    'forbidden': [{'label':'development','offset':0,'size':30000}],
    'consumed': [{'label':'old','offset':30000,'size':5000}],
}


class HoldoutGuardTests(unittest.TestCase):
    def test_development_overlap_is_never_confirmation(self):
        with self.assertRaisesRegex(ValueError, 'forbidden'):
            authorize_confirmation(FREEZE, 29999, 2, consume_new=True, reason='final check')

    def test_consumed_window_refuses_default_reuse(self):
        with self.assertRaisesRegex(ValueError, 'already consumed'):
            authorize_confirmation(FREEZE, 30000, 5000)

    def test_exact_reuse_requires_reason(self):
        with self.assertRaisesRegex(ValueError, 'non-empty reason'):
            authorize_confirmation(FREEZE, 30000, 5000, allow_reuse=True)
        result=authorize_confirmation(FREEZE,30000,5000,allow_reuse=True,reason='reproduce paper table')
        self.assertEqual(result['action'],'reuse')
        self.assertEqual(result['prior']['label'],'old')

    def test_partial_overlap_is_refused_even_with_reuse_override(self):
        with self.assertRaisesRegex(ValueError, 'partially overlaps'):
            authorize_confirmation(FREEZE, 32500, 5000, allow_reuse=True, reason='bad idea')

    def test_fresh_window_requires_explicit_consumption_and_reason(self):
        with self.assertRaisesRegex(ValueError, 'currently fresh'):
            authorize_confirmation(FREEZE, 35000, 5000)
        with self.assertRaisesRegex(ValueError, 'non-empty reason'):
            authorize_confirmation(FREEZE, 35000, 5000, consume_new=True)
        result=authorize_confirmation(FREEZE,35000,5000,consume_new=True,reason='final model selection')
        self.assertEqual(result['action'],'consume_new')

    def test_mutually_exclusive_overrides(self):
        with self.assertRaisesRegex(ValueError, 'either allow_reuse or consume_new'):
            authorize_confirmation(FREEZE,35000,5000,allow_reuse=True,consume_new=True,reason='x')

    def test_register_new_consumption_updates_manifest_and_blocks_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'freeze.json'
            path.write_text(json.dumps(FREEZE),encoding='utf-8')
            decision=authorize_confirmation(FREEZE,35000,5000,consume_new=True,reason='one final check')
            entry=register_consumption(path,decision,report=Path('reports/new.json'),config={'cap':640},result={'score':.9})
            self.assertEqual(entry['offset'],35000)
            updated=load_freeze(path)
            self.assertEqual(len(updated['consumed']),2)
            with self.assertRaisesRegex(ValueError,'already consumed'):
                authorize_confirmation(updated,35000,5000)

    def test_shipped_manifest_marks_both_known_confirmation_windows(self):
        path=Path(__file__).resolve().parents[1]/'reports/CONFIRMATION_FREEZE.json'
        freeze=load_freeze(path)
        windows={(int(x['offset']),int(x['size'])) for x in freeze['consumed']}
        self.assertIn((30000,5000),windows)
        self.assertIn((35000,5000),windows)
        self.assertTrue(any(int(x['offset'])==0 and int(x['size'])==30000 for x in freeze['forbidden']))

    def test_invalid_manifest_version_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'freeze.json'
            path.write_text(json.dumps({'version':2,'forbidden':[],'consumed':[]}),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Unsupported'):
                load_freeze(path)


if __name__=='__main__':
    unittest.main()
