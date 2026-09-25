"""Deterministic fingerprints and compatibility manifests for cached artifacts."""
from __future__ import annotations

import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any, Iterable


class StaleArtifactError(ValueError):
    """Raised when a cached artifact cannot be proven compatible with the current run."""


def _json_default(value: Any):
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"Cannot canonicalize {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Stable JSON representation suitable for hashing experiment identities."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def fingerprint(value: Any) -> str:
    """SHA256 of canonical JSON."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def source_file_sha256(obj: Any) -> str:
    """Hash the complete Python source file implementing a callable/class/module."""
    source = inspect.getsourcefile(obj)
    if not source:
        raise ValueError(f"Cannot locate source file for {obj!r}")
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


def file_signature(path: str | Path, sample_bytes: int = 65536) -> dict[str, Any]:
    """Cheap copy-stable signature using file size plus first/middle/last samples.

    This intentionally avoids hashing multi-GB artifacts in full. It is a stale-cache
    guard, not an adversarial content-authentication primitive.
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
    return {"size": size, "sample_sha256": h.hexdigest()}


def files_signature(paths: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
    """Sign several files while preserving their caller-supplied relative paths."""
    result = {}
    for item in paths:
        path = Path(item)
        result[path.as_posix()] = file_signature(path)
    return result


def write_manifest(path: str | Path, identity: Any) -> str:
    """Write an identity + checksum sidecar and return the identity fingerprint."""
    path = Path(path)
    digest = fingerprint(identity)
    payload = {"fingerprint": digest, "identity": identity}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    return digest


def read_manifest(path: str | Path) -> dict[str, Any] | None:
    """Read and self-validate a compatibility manifest."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        identity = payload["identity"]
        stored = payload["fingerprint"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise StaleArtifactError(f"Malformed compatibility manifest: {path}") from exc
    actual = fingerprint(identity)
    if stored != actual:
        raise StaleArtifactError(f"Compatibility manifest checksum mismatch: {path}")
    return payload


def require_manifest(path: str | Path, identity: Any, label: str = "artifact") -> str:
    """Fail unless an artifact manifest exactly matches the expected identity."""
    payload = read_manifest(path)
    expected = fingerprint(identity)
    if payload is None:
        raise StaleArtifactError(
            f"{label} has no compatibility manifest: {path}. "
            "Refresh/rebuild it instead of silently reusing a legacy cache."
        )
    if payload["fingerprint"] != expected:
        raise StaleArtifactError(
            f"{label} cache is stale/incompatible: stored {payload['fingerprint'][:12]}, "
            f"expected {expected[:12]}. Refresh/rebuild the artifact."
        )
    return expected


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def relation_fingerprint(connection, table: str, columns: Iterable[str]) -> dict[str, Any]:
    """Order-independent fingerprint of selected columns in a DuckDB relation."""
    columns = list(columns)
    if not _IDENTIFIER.fullmatch(table) or not columns or any(
        not _IDENTIFIER.fullmatch(column) for column in columns
    ):
        raise ValueError("Unsafe or empty relation fingerprint identifier")
    quoted = ",".join(f'"{column}"' for column in columns)
    row = connection.execute(
        f'SELECT count(*)::UBIGINT, '
        f'coalesce(bit_xor(hash({quoted})), 0::UBIGINT)::UBIGINT FROM "{table}"'
    ).fetchone()
    return {"rows": int(row[0]), "hash_xor": int(row[1]), "columns": columns}
