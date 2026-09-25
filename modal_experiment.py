"""Pure helpers for reproducible Team 517 Modal experiment runs.

This module intentionally depends only on the Python standard library so the same
spec validation can run locally (dry-run/tests) and inside a Modal worker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path, PurePosixPath
from typing import Iterable

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_MODULE = re.compile(r"^ber(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")
_INVOCATION = re.compile(r"^[0-9a-f]{20}$")
_MAX_ARGS = 128
_MAX_ARG_CHARS = 4096
_MAX_TOTAL_ARG_CHARS = 32768
_SAMPLE_BYTES = 65536


def _validate_name(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_NAME.fullmatch(value):
        raise ValueError(f"{field} must be 1-64 letters, digits, '.', '_' or '-', starting with alphanumeric")
    return value


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_args_json(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"args_json must be a JSON array of strings: {exc.msg}") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("args_json must be a JSON array of strings")
    if len(value) > _MAX_ARGS:
        raise ValueError(f"args_json may contain at most {_MAX_ARGS} arguments")
    if sum(len(item) for item in value) > _MAX_TOTAL_ARG_CHARS:
        raise ValueError("args_json is too large")
    for item in value:
        if len(item) > _MAX_ARG_CHARS:
            raise ValueError(f"individual arguments may be at most {_MAX_ARG_CHARS} characters")
        if "\x00" in item:
            raise ValueError("arguments may not contain NUL bytes")
    return value


def parse_required_paths_json(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"required_paths_json must be a JSON array of strings: {exc.msg}") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("required_paths_json must be a JSON array of strings")
    normalized: list[str] = []
    for item in value:
        path = PurePosixPath(item)
        if not item or path.is_absolute() or ".." in path.parts:
            raise ValueError("required paths must be non-empty paths relative to /volume without '..'")
        canonical = path.as_posix()
        if canonical.startswith("./"):
            canonical = canonical[2:]
        normalized.append(canonical)
    return normalized


def file_signature(path: Path, sample_bytes: int = _SAMPLE_BYTES) -> dict:
    """Cheap copy-stable signature for a large file.

    The signature samples first/middle/last regions and includes file size. It is
    intended to catch accidental stale-input reuse without hashing multi-GB files.
    """
    path = Path(path)
    size = path.stat().st_size
    sample_bytes = max(1, int(sample_bytes))
    offsets = sorted({0, max(0, size // 2 - sample_bytes // 2), max(0, size - sample_bytes)})
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for offset in offsets:
            handle.seek(offset)
            chunk = handle.read(sample_bytes)
            h.update(offset.to_bytes(8, "little", signed=False))
            h.update(len(chunk).to_bytes(8, "little", signed=False))
            h.update(chunk)
    return {"kind": "file", "size": size, "sample_sha256": h.hexdigest()}


def path_signature(path: Path) -> dict:
    path = Path(path)
    if path.is_file():
        return file_signature(path)
    if path.is_dir():
        files = {}
        for child in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: p.relative_to(path).as_posix()):
            files[child.relative_to(path).as_posix()] = file_signature(child)
        return {"kind": "directory", "files": files}
    raise FileNotFoundError(path)


def required_inputs_identity(volume_root: Path, required_paths: Iterable[str]) -> dict:
    """Fingerprint the actual required Volume snapshot, not only path strings."""
    volume_root = Path(volume_root)
    entries = {}
    for rel in parse_required_paths_json(json.dumps(list(required_paths))):
        entries[rel] = path_signature(volume_root / rel)
    return {"schema_version": 1, "entries": entries}


def required_inputs_fingerprint(volume_root: Path, required_paths: Iterable[str]) -> tuple[dict, str]:
    identity = required_inputs_identity(volume_root, required_paths)
    return identity, fingerprint(identity)


def build_spec(
    *,
    experiment_id: str,
    module: str,
    args: Iterable[str],
    required_paths: Iterable[str],
    code_sha: str,
    branch: str,
    run_name: str | None = None,
) -> dict:
    experiment_id = _validate_name(experiment_id, "experiment_id")
    if not isinstance(module, str) or not _MODULE.fullmatch(module):
        raise ValueError("module must be a dotted ber.* Python module")
    if not isinstance(code_sha, str) or not _SHA.fullmatch(code_sha):
        raise ValueError("code_sha must be a 7-64 character hexadecimal Git commit SHA")
    if not isinstance(branch, str) or not branch or len(branch) > 200 or any(ord(c) < 32 for c in branch):
        raise ValueError("branch must be a non-empty printable Git branch name up to 200 characters")
    args = parse_args_json(json.dumps(list(args)))
    required_paths = parse_required_paths_json(json.dumps(list(required_paths)))
    payload = {
        "schema_version": 2,
        "experiment_id": experiment_id,
        "module": module,
        "args": args,
        "required_paths": required_paths,
        "code_sha": code_sha.lower(),
        "branch": branch,
    }
    config_hash = fingerprint(payload)
    if run_name:
        run_name = _validate_name(run_name, "run_name")
    else:
        run_name = f"{experiment_id.lower()}-{config_hash[:12]}"
    payload["run_name"] = run_name
    payload["config_hash"] = config_hash
    return payload


def make_invocation_id() -> str:
    """Collision-resistant immutable attempt identifier."""
    return uuid.uuid4().hex[:20]


def validate_invocation_id(value: str) -> str:
    if not isinstance(value, str) or not _INVOCATION.fullmatch(value):
        raise ValueError("invocation_id must be exactly 20 lowercase hexadecimal characters")
    return value


def run_identity_hash(spec: dict, input_fingerprint: str) -> str:
    return fingerprint({
        "schema_version": 1,
        "config_hash": spec["config_hash"],
        "input_fingerprint": input_fingerprint,
    })


def resolve_args(args: Iterable[str], *, volume_root: Path, run_dir: Path) -> list[str]:
    replacements = {
        "{volume}": str(volume_root),
        "{run_dir}": str(run_dir),
        "{db}": str(volume_root / "project/artifacts/data.duckdb"),
        "{dataset}": str(volume_root / "dataset"),
    }
    resolved = []
    for arg in args:
        value = arg
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        resolved.append(value)
    return resolved


def command_for_spec(
    spec: dict,
    *,
    python_executable: str = sys.executable,
    volume_root: Path | None = None,
    run_dir: Path | None = None,
) -> list[str]:
    args = list(spec["args"])
    if volume_root is not None and run_dir is not None:
        args = resolve_args(args, volume_root=volume_root, run_dir=run_dir)
    return [python_executable, "-u", "-m", spec["module"], *args]


def run_group_directory(volume_root: Path, spec: dict, input_fingerprint: str) -> Path:
    identity = run_identity_hash(spec, input_fingerprint)
    return volume_root / "project/experiments" / spec["experiment_id"] / spec["run_name"] / identity[:16]


def run_directory(volume_root: Path, spec: dict, input_fingerprint: str, invocation_id: str) -> Path:
    invocation_id = validate_invocation_id(invocation_id)
    return run_group_directory(volume_root, spec, input_fingerprint) / invocation_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and print a Team 517 Modal experiment spec without executing it.")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--args-json", default="[]")
    parser.add_argument("--required-paths-json", default='["project/artifacts/data.duckdb"]')
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--run-name")
    ns = parser.parse_args()
    spec = build_spec(
        experiment_id=ns.experiment_id,
        module=ns.module,
        args=parse_args_json(ns.args_json),
        required_paths=parse_required_paths_json(ns.required_paths_json),
        code_sha=ns.code_sha,
        branch=ns.branch,
        run_name=ns.run_name,
    )
    preview_dir = Path("/volume/project/experiments") / spec["experiment_id"] / spec["run_name"] / "<input-hash>" / "<invocation-id>"
    preview = {
        **spec,
        "input_fingerprint": "<computed inside worker after volume.reload()>",
        "invocation_id": "<generated for each execution>",
        "run_dir": str(preview_dir),
        "command": command_for_spec(spec, volume_root=Path("/volume"), run_dir=preview_dir),
    }
    print(json.dumps(preview, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
