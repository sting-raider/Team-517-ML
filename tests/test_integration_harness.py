from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from integration_harness import IntegrationError, integrate_and_run


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, text=True,
                          capture_output=True, check=True)


class IntegrationHarnessTest(unittest.TestCase):
    def make_repo(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        repo = Path(self._tmp.name)
        run(repo, "init")
        run(repo, "config", "user.name", "Test User")
        run(repo, "config", "user.email", "test@example.invalid")
        (repo / "base.txt").write_text("base\n", encoding="utf-8")
        run(repo, "add", ".")
        run(repo, "commit", "-m", "base")
        run(repo, "branch", "-M", "main")
        return repo

    def tearDown(self) -> None:
        if getattr(self, "_tmp", None):
            self._tmp.cleanup()

    def add_branch(self, repo: Path, name: str, filename: str, content: str) -> None:
        run(repo, "checkout", "-b", name, "main")
        (repo / filename).write_text(content, encoding="utf-8")
        run(repo, "add", filename)
        run(repo, "commit", "-m", name)
        run(repo, "checkout", "main")

    def test_combines_refs_without_mutating_caller(self) -> None:
        repo = self.make_repo()
        self.add_branch(repo, "exp/a", "a.txt", "a\n")
        self.add_branch(repo, "exp/b", "b.txt", "b\n")
        main_before = run(repo, "rev-parse", "main").stdout.strip()
        output = repo / "result.json"
        result = integrate_and_run(
            repo, "main", ["exp/a", "exp/b"],
            ["python", "-c",
             "from pathlib import Path; assert Path('a.txt').exists() and Path('b.txt').exists()"],
            output_json=output,
        )
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.merge_order, ["exp/a", "exp/b"])
        self.assertEqual(run(repo, "rev-parse", "main").stdout.strip(), main_before)
        self.assertEqual(run(repo, "branch", "--show-current").stdout.strip(), "main")
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["base"]["sha"], main_before)
        self.assertEqual(payload["benchmark_exit_code"], 0)

    def test_fails_loudly_on_merge_conflict(self) -> None:
        repo = self.make_repo()
        run(repo, "checkout", "-b", "exp/a")
        (repo / "base.txt").write_text("a\n", encoding="utf-8")
        run(repo, "add", "base.txt"); run(repo, "commit", "-m", "a")
        run(repo, "checkout", "main"); run(repo, "checkout", "-b", "exp/b")
        (repo / "base.txt").write_text("b\n", encoding="utf-8")
        run(repo, "add", "base.txt"); run(repo, "commit", "-m", "b")
        run(repo, "checkout", "main")
        with self.assertRaises(IntegrationError):
            integrate_and_run(repo, "main", ["exp/a", "exp/b"],
                              ["python", "-c", "print('must not run')"])

    def test_rejects_dirty_caller(self) -> None:
        repo = self.make_repo()
        self.add_branch(repo, "exp/a", "a.txt", "a\n")
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(IntegrationError, "uncommitted changes"):
            integrate_and_run(repo, "main", ["exp/a"], ["python", "-c", "pass"])

    def test_records_failed_benchmark(self) -> None:
        repo = self.make_repo()
        self.add_branch(repo, "exp/a", "a.txt", "a\n")
        result = integrate_and_run(
            repo, "main", ["exp/a"],
            ["python", "-c", "raise SystemExit(7)"],
        )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.benchmark_exit_code, 7)

    def test_requires_ref(self) -> None:
        repo = self.make_repo()
        with self.assertRaisesRegex(IntegrationError, "at least one"):
            integrate_and_run(repo, "main", [], ["python", "-c", "pass"])


if __name__ == "__main__":
    unittest.main()
