"""Deterministic experiment report and registry-row rendering for swarm handoffs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RECOMMENDATIONS = {"PROMOTE", "REPLICATE", "REJECT", "FOLLOW-UP", "BLOCKED"}
REQUIRED_FIELDS = (
    "experiment_id",
    "issue_or_task",
    "pod",
    "owner",
    "branch",
    "commit",
    "hypothesis",
    "change",
    "protocol",
    "data_slice",
    "baseline",
    "result",
    "delta",
    "secondary_metrics",
    "runtime",
    "error_analysis",
    "interpretation",
    "risks",
    "recommendation",
    "follow_up_tasks",
)
REGISTRY_COLUMNS = (
    "experiment_id",
    "issue_or_task",
    "pod",
    "owner",
    "branch",
    "commit",
    "hypothesis",
    "data_slice",
    "baseline_metric",
    "new_metric",
    "delta",
    "secondary_metric",
    "runtime",
    "status",
    "report_path",
)


class ReportValidationError(ValueError):
    """Raised when an experiment record is incomplete or unsafe to render."""


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReportValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _render_value(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def _metric_text(metric: Any, field: str) -> str:
    if not isinstance(metric, dict):
        raise ReportValidationError(f"{field} must be an object with name and value")
    name = _require_text(metric.get("name"), f"{field}.name")
    if "value" not in metric:
        raise ReportValidationError(f"{field}.value is required")
    return f"{name}={_render_value(metric['value'])}"


def _as_lines(value: Any, field: str) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ReportValidationError(f"{field} must not be empty")
        return [text]
    if isinstance(value, list) and value:
        lines = []
        for i, item in enumerate(value):
            lines.append(_require_text(item, f"{field}[{i}]"))
        return lines
    raise ReportValidationError(f"{field} must be a non-empty string or list of strings")


def validate_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ReportValidationError("experiment record must be a JSON object")
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise ReportValidationError("missing required fields: " + ", ".join(missing))

    normalized = dict(record)
    for field in ("experiment_id", "pod", "owner", "branch", "commit", "hypothesis", "change", "protocol", "data_slice", "runtime", "interpretation"):
        normalized[field] = _require_text(record[field], field)

    issue = record["issue_or_task"]
    if not isinstance(issue, (str, int)) or (isinstance(issue, str) and not issue.strip()):
        raise ReportValidationError("issue_or_task must be a non-empty string or integer")
    normalized["issue_or_task"] = str(issue).strip()

    recommendation = _require_text(record["recommendation"], "recommendation").upper()
    if recommendation not in RECOMMENDATIONS:
        allowed = ", ".join(sorted(RECOMMENDATIONS))
        raise ReportValidationError(f"recommendation must be one of: {allowed}")
    normalized["recommendation"] = recommendation

    _metric_text(record["baseline"], "baseline")
    _metric_text(record["result"], "result")
    if isinstance(record["delta"], (dict, list)):
        raise ReportValidationError("delta must be a scalar value")

    secondary = record["secondary_metrics"]
    if not isinstance(secondary, dict) or not secondary:
        raise ReportValidationError("secondary_metrics must be a non-empty object")
    normalized["secondary_metrics"] = {str(k): v for k, v in sorted(secondary.items(), key=lambda kv: str(kv[0]))}

    normalized["error_analysis"] = _as_lines(record["error_analysis"], "error_analysis")
    normalized["risks"] = _as_lines(record["risks"], "risks")

    follow = record["follow_up_tasks"]
    if not isinstance(follow, list):
        raise ReportValidationError("follow_up_tasks must be a list")
    normalized["follow_up_tasks"] = [_require_text(x, f"follow_up_tasks[{i}]") for i, x in enumerate(follow)]

    commands = record.get("commands", [])
    if not isinstance(commands, list):
        raise ReportValidationError("commands must be a list when provided")
    normalized["commands"] = [_require_text(x, f"commands[{i}]") for i, x in enumerate(commands)]

    compliance = record.get("compliance")
    if compliance is not None:
        normalized["compliance"] = _require_text(compliance, "compliance")

    report_path = record.get("report_path")
    if report_path is not None:
        normalized["report_path"] = _require_text(report_path, "report_path")

    return normalized


def _bullet_section(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def render_markdown(record: Any) -> str:
    r = validate_record(record)
    baseline = _metric_text(r["baseline"], "baseline")
    result = _metric_text(r["result"], "result")
    secondary = "\n".join(f"- {key}: {_render_value(value)}" for key, value in r["secondary_metrics"].items())
    command_block = ""
    if r["commands"]:
        commands = "\n".join(r["commands"])
        command_block = f"\n\nCommands:\n\n```bash\n{commands}\n```"
    compliance = ""
    if r.get("compliance"):
        compliance = f"\n\nCompliance: {r['compliance']}"
    follow_up = _bullet_section(r["follow_up_tasks"]) if r["follow_up_tasks"] else "None."

    return (
        f"# {r['experiment_id']} — Experiment report\n\n"
        f"## Hypothesis\n\n{r['hypothesis']}\n\n"
        f"## Change\n\n{r['change']}\n\n"
        f"## Protocol\n\n{r['protocol']}\n\n"
        f"Data slice: {r['data_slice']}\n\n"
        f"Branch/commit: `{r['branch']}` / `{r['commit']}`"
        f"{command_block}{compliance}\n\n"
        f"## Results\n\n"
        f"- Baseline: {baseline}\n"
        f"- New result: {result}\n"
        f"- Delta: {_render_value(r['delta'])}\n"
        f"- Runtime: {r['runtime']}\n"
        f"- Secondary metrics:\n{secondary}\n\n"
        f"## Error analysis\n\n{_bullet_section(r['error_analysis'])}\n\n"
        f"## Interpretation\n\n{r['interpretation']}\n\n"
        f"## Risks\n\n{_bullet_section(r['risks'])}\n\n"
        f"## Recommendation\n\n**{r['recommendation']}**\n\n"
        f"## Follow-up tasks\n\n{follow_up}\n"
    )


def registry_row(record: Any) -> str:
    r = validate_record(record)
    report_path = _require_text(r.get("report_path"), "report_path")
    values = {
        "experiment_id": r["experiment_id"],
        "issue_or_task": r["issue_or_task"],
        "pod": r["pod"],
        "owner": r["owner"],
        "branch": r["branch"],
        "commit": r["commit"],
        "hypothesis": r["hypothesis"],
        "data_slice": r["data_slice"],
        "baseline_metric": _metric_text(r["baseline"], "baseline"),
        "new_metric": _metric_text(r["result"], "result"),
        "delta": _render_value(r["delta"]),
        "secondary_metric": "; ".join(f"{k}={_render_value(v)}" for k, v in r["secondary_metrics"].items()),
        "runtime": r["runtime"],
        "status": r["recommendation"],
        "report_path": report_path,
    }
    fields = []
    for column in REGISTRY_COLUMNS:
        value = str(values[column]).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
        fields.append(value)
    return "\t".join(fields)


def main() -> None:
    p = argparse.ArgumentParser(description="Validate and render a Team 517 experiment report")
    p.add_argument("--input", type=Path, required=True, help="experiment JSON")
    p.add_argument("--output", type=Path, required=True, help="Markdown report path")
    p.add_argument("--registry-row-out", type=Path, help="optional one-line TSV registry row")
    args = p.parse_args()

    record = json.loads(args.input.read_text(encoding="utf-8"))
    markdown = render_markdown(record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    if args.registry_row_out:
        args.registry_row_out.parent.mkdir(parents=True, exist_ok=True)
        args.registry_row_out.write_text(registry_row(record) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
