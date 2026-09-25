import sys
import tempfile
import types
import unittest
from pathlib import Path

# data.py imports duckdb at module load; these tests exercise the provenance-only
# helpers and remain runnable in restricted environments without the wheel.
if "duckdb" not in sys.modules:
    try:
        import duckdb  # noqa: F401
    except ModuleNotFoundError:
        sys.modules["duckdb"] = types.SimpleNamespace(connect=None)

from ber.data import prep_contract_fingerprint, split_input_identity


class PreparedDataProvenanceTests(unittest.TestCase):
    def _write_split(self, root, split="train"):
        directory = root / split
        directory.mkdir(parents=True)
        for source in (1, 2, 3):
            (directory / f"{split}_source{source}.tsv").write_bytes(
                (f"source-{source}-" * 20000).encode("utf-8")
            )

    def test_split_identity_is_stable_for_unchanged_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_split(root)
            first = split_input_identity(root, "train")
            second = split_input_identity(root, "train")
            self.assertEqual(first, second)
            self.assertEqual(first["prep_contract"], prep_contract_fingerprint())
            self.assertEqual(
                sorted(first["files"]),
                ["train_source1.tsv", "train_source2.tsv", "train_source3.tsv"],
            )

    def test_split_identity_changes_when_one_raw_source_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_split(root)
            first = split_input_identity(root, "train")
            path = root / "train" / "train_source2.tsv"
            data = bytearray(path.read_bytes())
            data[len(data) // 2] ^= 1
            path.write_bytes(data)
            second = split_input_identity(root, "train")
            self.assertNotEqual(first, second)
            self.assertEqual(
                first["files"]["train_source1.tsv"],
                second["files"]["train_source1.tsv"],
            )
            self.assertNotEqual(
                first["files"]["train_source2.tsv"],
                second["files"]["train_source2.tsv"],
            )


if __name__ == "__main__":
    unittest.main()
