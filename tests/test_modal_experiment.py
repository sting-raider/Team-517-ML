import json
import shutil
import tempfile
import unittest
from pathlib import Path

from modal_experiment import (
    build_spec,
    command_for_spec,
    file_signature,
    make_invocation_id,
    parse_args_json,
    parse_required_paths_json,
    required_inputs_fingerprint,
    run_directory,
    run_identity_hash,
)


class ModalExperimentSpecTests(unittest.TestCase):
    def _spec(self):
        return build_spec(
            experiment_id="R003",
            module="ber.retrieval_char_address",
            args=["--db", "{db}", "--out", "{run_dir}"],
            required_paths=["project/artifacts/data.duckdb"],
            code_sha="a" * 40,
            branch="agent/r/R003-char-address",
        )

    def test_spec_is_deterministic_and_resolves_paths(self):
        first = self._spec()
        second = self._spec()
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], 2)
        self.assertTrue(first["run_name"].startswith("r003-"))
        run_dir = run_directory(Path("/volume"), first, "f" * 64, "a" * 20)
        command = command_for_spec(
            first,
            python_executable="python",
            volume_root=Path("/volume"),
            run_dir=run_dir,
        )
        self.assertEqual(command[:4], ["python", "-u", "-m", "ber.retrieval_char_address"])
        self.assertIn("/volume/project/artifacts/data.duckdb", command)
        self.assertIn(str(run_dir), command)

    def test_hash_changes_with_args_or_commit(self):
        base = dict(
            experiment_id="I004",
            module="ber.metrics",
            args=[],
            required_paths=[],
            code_sha="b" * 40,
            branch="agent/i/I004-modal-experiment-runner",
        )
        first = build_spec(**base)
        changed_args = build_spec(**{**base, "args": ["--x", "1"]})
        changed_sha = build_spec(**{**base, "code_sha": "c" * 40})
        self.assertNotEqual(first["config_hash"], changed_args["config_hash"])
        self.assertNotEqual(first["config_hash"], changed_sha["config_hash"])

    def test_rejects_shellish_module_and_unsafe_required_path(self):
        with self.assertRaisesRegex(ValueError, r"ber\.\*"):
            build_spec(
                experiment_id="R003",
                module="os.system",
                args=[],
                required_paths=[],
                code_sha="d" * 40,
                branch="agent/r/R003",
            )
        with self.assertRaisesRegex(ValueError, r"without '\.\.'"):
            parse_required_paths_json(json.dumps(["../secrets"]))

    def test_args_json_requires_string_array(self):
        with self.assertRaisesRegex(ValueError, "array of strings"):
            parse_args_json('["ok", 3]')
        self.assertEqual(parse_args_json('["--cap", "640"]'), ["--cap", "640"])

    def test_file_signature_is_copy_stable_and_content_sensitive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = bytearray(b"a" * 200000)
            original = root / "a.bin"
            copied = root / "b.bin"
            original.write_bytes(payload)
            shutil.copyfile(original, copied)
            first = file_signature(original)
            self.assertEqual(first, file_signature(copied))
            payload[100000:100016] = b"changed-middle!!"
            original.write_bytes(payload)
            self.assertNotEqual(first, file_signature(original))

    def test_required_input_snapshot_changes_run_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "project/artifacts/data.duckdb"
            db.parent.mkdir(parents=True)
            db.write_bytes(b"x" * 150000)
            spec = self._spec()
            identity1, fp1 = required_inputs_fingerprint(root, spec["required_paths"])
            identity2, fp2 = required_inputs_fingerprint(root, spec["required_paths"])
            self.assertEqual(identity1, identity2)
            self.assertEqual(fp1, fp2)
            run1 = run_identity_hash(spec, fp1)
            db.write_bytes(b"y" * 150000)
            _, fp3 = required_inputs_fingerprint(root, spec["required_paths"])
            self.assertNotEqual(fp1, fp3)
            self.assertNotEqual(run1, run_identity_hash(spec, fp3))

    def test_invocation_ids_and_directories_are_unique_but_same_identity(self):
        spec = self._spec()
        ids = {make_invocation_id() for _ in range(64)}
        self.assertEqual(len(ids), 64)
        self.assertTrue(all(len(value) == 20 and set(value) <= set("0123456789abcdef") for value in ids))
        dirs = {run_directory(Path("/volume"), spec, "f" * 64, value) for value in ids}
        self.assertEqual(len(dirs), 64)
        identity = run_identity_hash(spec, "f" * 64)
        self.assertTrue(all(identity[:16] in str(path) for path in dirs))


if __name__ == "__main__":
    unittest.main()
