import csv
import tempfile
import unittest
from pathlib import Path

from ber.submission_ledger import FIELDS, append_row, record_score, validate_ledger


def base_row(submission_id="run-1"):
    row = {field: "" for field in FIELDS}
    row.update(
        submission_id=submission_id,
        status="GENERATED",
        candidate_cap="160",
        threshold="0.575",
        local_protocol="calibration_4389_cap160",
        local_macro_f0_5="0.927",
        candidate_pair_recall="0.925",
        mean_candidates="142.18",
        p90_candidates="160",
    )
    return row


class SubmissionLedgerTests(unittest.TestCase):
    def test_generated_row_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.tsv"
            result = append_row(path, base_row())
            self.assertEqual(result, {"status": "PASS", "rows": 1, "submitted": 0, "scored": 0})
            self.assertEqual(validate_ledger(path), result)

    def test_duplicate_submission_id_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.tsv"
            append_row(path, base_row())
            with self.assertRaisesRegex(ValueError, "duplicate submission_id"):
                append_row(path, base_row())

    def test_submitted_requires_immutable_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.tsv"
            row = base_row()
            row["status"] = "SUBMITTED"
            row["submitted_utc"] = "2026-09-25T16:00:00Z"
            with self.assertRaisesRegex(ValueError, "lacks immutable provenance"):
                append_row(path, row)

    def test_record_score_is_informational_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.tsv"
            row = base_row()
            row.update(
                status="SUBMITTED",
                submitted_utc="2026-09-25T16:00:00Z",
                code_sha="a" * 40,
                model_config_sha256="b" * 64,
                matching_sha256="c" * 64,
                candidate_sha256="d" * 64,
            )
            append_row(path, row)
            result = record_score(path, "run-1", public_score=0.91)
            self.assertEqual(result["scored"], 1)
            with path.open(newline="", encoding="utf-8") as handle:
                saved = next(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(saved["public_score"], "0.91")
            self.assertEqual(saved["feedback_usage"], "informational_only")

    def test_score_rejected_before_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.tsv"
            append_row(path, base_row())
            with self.assertRaisesRegex(ValueError, "SUBMITTED"):
                record_score(path, "run-1", public_score=0.9)

    def test_nonfinite_and_out_of_range_metrics_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in ("nan", "inf", "-0.1", "1.1"):
                path = Path(tmp) / (value.replace("-", "neg") + ".tsv")
                row = base_row()
                row["local_macro_f0_5"] = value
                with self.assertRaises(ValueError):
                    append_row(path, row)

    def test_leaderboard_score_cannot_be_mislabeled_as_local_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.tsv"
            row = base_row()
            row.update(
                status="SUBMITTED",
                submitted_utc="2026-09-25T16:00:00Z",
                code_sha="a" * 40,
                model_config_sha256="b" * 64,
                matching_sha256="c" * 64,
                candidate_sha256="d" * 64,
                public_score="0.9",
                feedback_usage="training_signal",
            )
            with self.assertRaisesRegex(ValueError, "informational_only"):
                append_row(path, row)


if __name__ == "__main__":
    unittest.main()
