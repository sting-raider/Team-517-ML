import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ber.provenance import (
    StaleArtifactError,
    file_signature,
    fingerprint,
    relation_fingerprint,
    require_manifest,
    write_manifest,
)


class _FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self):
        self.sql = None

    def execute(self, sql):
        self.sql = sql
        return _FakeResult((7, 123456789))


class ProvenanceTests(unittest.TestCase):
    def test_canonical_fingerprint_is_dict_order_independent(self):
        self.assertEqual(
            fingerprint({"b": 2, "a": {"z": 3, "x": 1}}),
            fingerprint({"a": {"x": 1, "z": 3}, "b": 2}),
        )

    def test_file_signature_is_copy_stable_and_content_sensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "a.bin"
            copied = root / "b.bin"
            original.write_bytes(b"a" * 70000 + b"middle" + b"z" * 70000)
            shutil.copyfile(original, copied)
            self.assertEqual(file_signature(original), file_signature(copied))
            copied.write_bytes(b"a" * 70000 + b"change" + b"z" * 70000)
            self.assertNotEqual(file_signature(original), file_signature(copied))

    def test_manifest_detects_config_change_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            identity = {"cap": 640, "features": ["a", "b"]}
            write_manifest(path, identity)
            require_manifest(path, {"features": ["a", "b"], "cap": 640}, "feature cache")
            with self.assertRaisesRegex(StaleArtifactError, "stale/incompatible"):
                require_manifest(path, {"cap": 320, "features": ["a", "b"]}, "feature cache")
            payload = json.loads(path.read_text())
            payload["identity"]["cap"] = 20
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(StaleArtifactError, "checksum mismatch"):
                require_manifest(path, identity, "feature cache")

    def test_missing_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(StaleArtifactError, "no compatibility manifest"):
                require_manifest(Path(tmp) / "missing.json", {"x": 1}, "trial")

    def test_relation_fingerprint_contract_and_identifier_validation(self):
        connection = _FakeConnection()
        result = relation_fingerprint(connection, "candidates", ["anchor", "rid"])
        self.assertEqual(
            result,
            {"rows": 7, "hash_xor": 123456789, "columns": ["anchor", "rid"]},
        )
        self.assertIn('hash("anchor","rid")', connection.sql)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            relation_fingerprint(connection, "candidates;DROP TABLE train", ["anchor"])


if __name__ == "__main__":
    unittest.main()
