"""Deterministically reconcile concurrent experiment registry versions.

This utility exists because swarm branches are required to update the same
experiments/REGISTRY.tsv file. It unions complete registry versions by
experiment_id, deduplicates identical rows, and fails loudly on conflicts.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Iterable

HEADER = (
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


class RegistryError(ValueError):
    """Raised when a registry cannot be reconciled safely."""


def read_registry(path: Path) -> list[tuple[str, ...]]:
    """Read and strictly validate one complete REGISTRY.tsv."""
    rows: list[tuple[str, ...]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = tuple(next(reader))
        except StopIteration as exc:
            raise RegistryError(f"{path}: empty registry") from exc
        if header != HEADER:
            raise RegistryError(
                f"{path}: header mismatch; expected {HEADER!r}, got {header!r}"
            )
        for line_no, row in enumerate(reader, start=2):
            if len(row) != len(HEADER):
                raise RegistryError(
                    f"{path}:{line_no}: expected {len(HEADER)} columns, got {len(row)}"
                )
            values = tuple(row)
            if not values[0].strip():
                raise RegistryError(f"{path}:{line_no}: empty experiment_id")
            rows.append(values)
    return rows


def reconcile(paths: Iterable[Path]) -> list[tuple[str, ...]]:
    """Union registry rows by experiment_id with provenance-aware conflicts."""
    paths = [Path(path) for path in paths]
    if len(paths) < 2:
        raise RegistryError("at least two registry versions are required")

    by_id: dict[str, tuple[str, ...]] = {}
    origins: dict[str, str] = {}
    for path in paths:
        for row in read_registry(path):
            experiment_id = row[0]
            previous = by_id.get(experiment_id)
            if previous is None:
                by_id[experiment_id] = row
                origins[experiment_id] = str(path)
                continue
            if previous != row:
                raise RegistryError(
                    "conflicting rows for experiment_id "
                    f"{experiment_id!r}: {origins[experiment_id]} vs {path}"
                )

    return [by_id[key] for key in sorted(by_id)]


def render(rows: Iterable[tuple[str, ...]]) -> str:
    """Render canonical TSV text with a stable final newline."""
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buffer.getvalue()


def write_atomic(path: Path, content: str) -> None:
    """Write the reconciled registry atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="")
    os.replace(temp, path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Union concurrent Team 517 experiment registries safely."
    )
    parser.add_argument(
        "registries",
        nargs="+",
        type=Path,
        help="Complete REGISTRY.tsv versions to union (at least two).",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path for the reconciled REGISTRY.tsv.",
    )
    args = parser.parse_args()

    try:
        rows = reconcile(args.registries)
        write_atomic(args.output, render(rows))
    except RegistryError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
