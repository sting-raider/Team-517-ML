import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ber.reporting import ReportValidationError, registry_row, render_markdown, validate_record


def sample_record():
    return {
        "experiment_id": "I013",
        "issue_or_task": 105,
        "pod": "I",
        "owner": "ChatGPT/Pod I",
        "branch": "agent/i/I013-auto-report",
        "commit": "abc123",
        "hypothesis": "Structured rendering reduces incomplete handoffs.",
        "change": "Added deterministic validation and rendering.",
        "protocol": "Synthetic Tier 0/1 validation only; no holdout consumed.",
        "data_slice": "synthetic fixtures only",
        "baseline": {"name": "report_validation", "value": "manual"},
        "result": {"name": "report_validation", "value": "automated"},
        "delta": "NA",
        "secondary_metrics": {"cli_smoke": "PASS", "unit_tests": 5},
        "runtime": "<1s synthetic",
        "error_analysis": ["Missing fields fail loudly.", "Invalid recommendations fail loudly."],
        "interpretation": "The renderer standardizes handoffs without touching model behavior.",
        "risks": ["A renderer cannot verify that claimed metrics are scientifically valid."],
        "recommendation": "PROMOTE",
        "follow_up_tasks": ["Wire into benchmark emitters after their schemas stabilize."],
        "commands": ["PYTHONPATH=src python -m unittest tests.test_reporting -v"],
        "compliance": "No challenge data or external identity data used.",
        "report_path": "reports/swarm/I013-auto-report.md",
    }


class ReportingTests(unittest.TestCase):
    def test_deterministic_markdown(self):
        record = sample_record()
        first = render_markdown(record)
        second = render_markdown(record)
        self.assertEqual(first, second)
        self.assertIn("## Hypothesis", first)
        self.assertIn("## Error analysis", first)
        self.assertIn("**PROMOTE**", first)
        self.assertLess(first.index("cli_smoke"), first.index("unit_tests"))

    def test_missing_required_field_fails(self):
        record = sample_record()
        del record["protocol"]
        with self.assertRaisesRegex(ReportValidationError, "missing required fields: protocol"):
            validate_record(record)

    def test_invalid_recommendation_fails(self):
        record = sample_record()
        record["recommendation"] = "MAYBE"
        with self.assertRaisesRegex(ReportValidationError, "recommendation must be one of"):
            validate_record(record)

    def test_registry_row_is_one_line_and_column_complete(self):
        record = sample_record()
        record["hypothesis"] = "Line one\nline two\twith tab"
        row = registry_row(record)
        self.assertNotIn("\n", row)
        self.assertEqual(len(row.split("\t")), 15)
        self.assertTrue(row.endswith("reports/swarm/I013-auto-report.md"))

    def test_cli_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            inp = tmp / "record.json"
            out = tmp / "report.md"
            reg = tmp / "row.tsv"
            inp.write_text(json.dumps(sample_record()), encoding="utf-8")
            env = dict(__import__("os").environ)
            env["PYTHONPATH"] = str(ROOT / "src")
            proc = subprocess.run(
                [sys.executable, "-m", "ber.reporting", "--input", str(inp), "--output", str(out), "--registry-row-out", str(reg)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("# I013 — Experiment report", out.read_text(encoding="utf-8"))
            self.assertEqual(len(reg.read_text(encoding="utf-8").rstrip("\n").split("\t")), 15)


if __name__ == "__main__":
    unittest.main()
