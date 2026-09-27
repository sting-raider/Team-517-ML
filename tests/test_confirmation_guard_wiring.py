import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def function_source(path, name):
    text = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = text.splitlines()
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"{name} not found in {path}")


class ConfirmationGuardWiringTests(unittest.TestCase):
    def test_shared_v2_selection_requires_reuse_authorization(self):
        block = function_source("src/ber/v2.py", "select_anchors")
        self.assertIn("require_confirmation_reuse", block)
        self.assertIn("confirmation_reason", block)
        self.assertLess(
            block.index("require_confirmation_reuse"),
            block.index("condition = f'sample_position>"),
        )

    def test_modal_v2_guards_cache_and_score_observation(self):
        materialize = function_source("modal_v2.py", "make_features")
        score = function_source("modal_v2.py", "confirm_model")
        self.assertIn("require_confirmation_reuse", materialize)
        self.assertLess(
            materialize.index("require_confirmation_reuse"),
            materialize.index("ready.json"),
        )
        self.assertIn("require_confirmation_reuse", score)
        self.assertIn("holdout_guard", score)

    def test_modal_v3_guards_cache_and_score_observation(self):
        materialize = function_source("modal_v3.py", "make_features")
        score = function_source("modal_v3.py", "confirm_model")
        self.assertIn("require_confirmation_reuse", materialize)
        self.assertLess(
            materialize.index("require_confirmation_reuse"),
            materialize.index("ready.json"),
        )
        self.assertIn("require_confirmation_reuse", score)
        self.assertIn("holdout_guard", score)

    def test_modal_local_entrypoints_require_reason(self):
        for path in ("modal_v2.py", "modal_v3.py"):
            block = function_source(path, "main")
            self.assertIn("if not reason.strip()", block)
            self.assertIn("Historical confirmation reuse requires --reason", block)

    def test_readme_does_not_run_confirmation_routinely(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("python -m ber.confirm\n", text)
        self.assertIn("CONFIRMATION_FREEZE.json", text)


if __name__ == "__main__":
    unittest.main()
