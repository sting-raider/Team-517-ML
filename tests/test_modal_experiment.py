import json
import unittest
from pathlib import Path

from modal_experiment import (
    build_spec,
    command_for_spec,
    parse_args_json,
    parse_required_paths_json,
    run_directory,
)


class ModalExperimentSpecTests(unittest.TestCase):
    def test_spec_is_deterministic_and_resolves_paths(self):
        kwargs = dict(
            experiment_id="R003",
            module="ber.retrieval_char_address",
            args=["--db", "{db}", "--out", "{run_dir}"],
            required_paths=["project/artifacts/data.duckdb"],
            code_sha="a" * 40,
            branch="agent/r/R003-char-address",
        )
        first = build_spec(**kwargs)
        second = build_spec(**kwargs)
        self.assertEqual(first, second)
        self.assertTrue(first["run_name"].startswith("r003-"))
        run_dir = run_directory(Path("/volume"), first)
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


if __name__ == "__main__":
    unittest.main()
