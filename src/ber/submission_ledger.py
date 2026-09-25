"""Validate the committed leaderboard submission ledger.

Leaderboard feedback is provenance only. This module deliberately has no import
path into training/evaluation code and never exposes leaderboard scores as model
features or labels.
"""
import argparse
import csv
import json
import math
import re
from pathlib import Path

FIELDS = [
    "submission_id",
    "status",
    "submitted_utc",
    "code_sha",
    "model_config_sha256",
    "matching_sha256",
    "candidate_sha256",
    "candidate_cap",
    "threshold",
    "local_protocol",
    "local_macro_f0_5",
    "candidate_pair_recall",
    "mean_candidates",
    "p90_candidates",
    "test_anchors",
    "test_candidate_pairs",
    "test_predicted_matches",
    "public_score",
    "private_score",
    "feedback_usage",
    "notes",
]
STATUSES = {"GENERATED", "SUBMITTED", "INVALIDATED"}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def _optional_int(row, field):
    value = row[field].strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"{field} must be nonnegative")
    return parsed


def _optional_float(row, field, low=None, high=None):
    value = row[field].strip()
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be numeric: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    if low is not None and parsed < low:
        raise ValueError(f"{field} must be >= {low}")
    if high is not None and parsed > high:
        raise ValueError(f"{field} must be <= {high}")
    return parsed


def _validate_row(row, seen):
    missing = [field for field in FIELDS if field not in row]
    extra = [field for field in row if field not in FIELDS]
    if missing or extra:
        raise ValueError(f"ledger columns mismatch; missing={missing}, extra={extra}")

    submission_id = row["submission_id"].strip()
    if not ID.fullmatch(submission_id):
        raise ValueError(f"invalid submission_id: {submission_id!r}")
    if submission_id in seen:
        raise ValueError(f"duplicate submission_id: {submission_id}")
    seen.add(submission_id)

    status = row["status"].strip()
    if status not in STATUSES:
        raise ValueError(f"invalid status for {submission_id}: {status!r}")

    submitted_utc = row["submitted_utc"].strip()
    if submitted_utc and not UTC.fullmatch(submitted_utc):
        raise ValueError(f"submitted_utc must be UTC YYYY-MM-DDTHH:MM:SSZ: {submission_id}")

    code_sha = row["code_sha"].strip().lower()
    if code_sha and not HEX40.fullmatch(code_sha):
        raise ValueError(f"code_sha must be a 40-character lowercase hex SHA: {submission_id}")
    for field in ("model_config_sha256", "matching_sha256", "candidate_sha256"):
        value = row[field].strip().lower()
        if value and not HEX64.fullmatch(value):
            raise ValueError(f"{field} must be a 64-character lowercase hex digest: {submission_id}")

    _optional_int(row, "candidate_cap")
    _optional_int(row, "test_anchors")
    _optional_int(row, "test_candidate_pairs")
    _optional_int(row, "test_predicted_matches")
    _optional_float(row, "threshold", 0.0, 1.0)
    _optional_float(row, "local_macro_f0_5", 0.0, 1.0)
    _optional_float(row, "candidate_pair_recall", 0.0, 1.0)
    _optional_float(row, "mean_candidates", 0.0)
    _optional_float(row, "p90_candidates", 0.0)
    public_score = _optional_float(row, "public_score", 0.0, 1.0)
    private_score = _optional_float(row, "private_score", 0.0, 1.0)

    if status == "SUBMITTED":
        required = (
            "submitted_utc",
            "code_sha",
            "model_config_sha256",
            "matching_sha256",
            "candidate_sha256",
        )
        absent = [field for field in required if not row[field].strip()]
        if absent:
            raise ValueError(f"SUBMITTED row {submission_id} lacks immutable provenance: {absent}")

    if public_score is not None or private_score is not None:
        if status != "SUBMITTED":
            raise ValueError(f"leaderboard score requires SUBMITTED status: {submission_id}")
        if row["feedback_usage"].strip() != "informational_only":
            raise ValueError(
                f"leaderboard score must be marked informational_only and never used as training/eval labels: {submission_id}"
            )
    elif row["feedback_usage"].strip() not in ("", "informational_only"):
        raise ValueError(f"invalid feedback_usage for {submission_id}")

    if row["local_macro_f0_5"].strip() and not row["local_protocol"].strip():
        raise ValueError(f"local metric requires an explicit local_protocol: {submission_id}")


def _read(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != FIELDS:
            raise ValueError(f"ledger header mismatch: {reader.fieldnames!r}")
        return list(reader)


def _write(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def validate_ledger(path):
    rows = _read(path)
    seen = set()
    for row in rows:
        _validate_row(row, seen)
    return {
        "status": "PASS",
        "rows": len(rows),
        "submitted": sum(row["status"] == "SUBMITTED" for row in rows),
        "scored": sum(bool(row["public_score"].strip() or row["private_score"].strip()) for row in rows),
    }


def append_row(path, row):
    path = Path(path)
    rows = _read(path) if path.exists() else []
    seen = set()
    for existing in rows:
        _validate_row(existing, seen)
    normalized = {field: str(row.get(field, "")) for field in FIELDS}
    extra = sorted(set(row) - set(FIELDS))
    if extra:
        raise ValueError(f"unknown ledger fields: {extra}")
    _validate_row(normalized, seen)
    rows.append(normalized)
    _write(path, rows)
    return validate_ledger(path)


def record_score(path, submission_id, public_score=None, private_score=None):
    if public_score is None and private_score is None:
        raise ValueError("provide at least one leaderboard score")
    rows = _read(path)
    matches = [row for row in rows if row["submission_id"] == submission_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one submission_id={submission_id!r}, found {len(matches)}")
    row = matches[0]
    if row["status"] != "SUBMITTED":
        raise ValueError("leaderboard scores may only be recorded for SUBMITTED rows")
    if public_score is not None:
        row["public_score"] = str(public_score)
    if private_score is not None:
        row["private_score"] = str(private_score)
    row["feedback_usage"] = "informational_only"
    seen = set()
    for candidate in rows:
        _validate_row(candidate, seen)
    _write(path, rows)
    return validate_ledger(path)


def main():
    parser = argparse.ArgumentParser(description="Validate/update the Team 517 submission ledger")
    parser.add_argument("--ledger", type=Path, default=Path("submissions/LEDGER.tsv"))
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("validate")

    add = sub.add_parser("append")
    add.add_argument("--row-json", type=Path, required=True)

    score = sub.add_parser("record-score")
    score.add_argument("--submission-id", required=True)
    score.add_argument("--public-score", type=float)
    score.add_argument("--private-score", type=float)

    args = parser.parse_args()
    if args.action == "validate":
        result = validate_ledger(args.ledger)
    elif args.action == "append":
        row = json.loads(args.row_json.read_text(encoding="utf-8"))
        if not isinstance(row, dict):
            raise ValueError("row JSON must contain one object")
        result = append_row(args.ledger, row)
    else:
        result = record_score(
            args.ledger,
            args.submission_id,
            public_score=args.public_score,
            private_score=args.private_score,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
