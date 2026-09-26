"""Fail-closed confirmation-window authorization shared by all evaluation paths."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


DEFAULT_FREEZE = Path(__file__).resolve().parents[2] / "reports" / "CONFIRMATION_FREEZE.json"


def canonical_sha256(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_window(offset: int, size: int) -> None:
    if offset < 0:
        raise ValueError("confirmation offset must be non-negative")
    if size <= 0:
        raise ValueError("confirmation size must be positive")


def _overlap(a_offset: int, a_size: int, b_offset: int, b_size: int) -> bool:
    return max(a_offset, b_offset) < min(a_offset + a_size, b_offset + b_size)


def load_freeze(path: Path | None = None) -> dict:
    path = Path(path or DEFAULT_FREEZE)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError(f"Unsupported confirmation freeze version: {data.get('version')!r}")
    for key in ("forbidden", "consumed"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"Confirmation freeze must contain a {key!r} list")
        for entry in data[key]:
            _validate_window(int(entry["offset"]), int(entry["size"]))
    return data


def authorize_confirmation(
    freeze: dict,
    offset: int,
    size: int,
    *,
    allow_reuse: bool = False,
    consume_new: bool = False,
    reason: str | None = None,
) -> dict:
    """Authorize one window without inspecting labels or model outputs."""
    _validate_window(offset, size)
    if allow_reuse and consume_new:
        raise ValueError("Choose either allow_reuse or consume_new, not both")
    reason = (reason or "").strip()

    forbidden = [
        entry for entry in freeze.get("forbidden", [])
        if _overlap(offset, size, int(entry["offset"]), int(entry["size"]))
    ]
    if forbidden:
        labels = ", ".join(str(entry.get("label", "reserved")) for entry in forbidden)
        raise ValueError(f"Requested confirmation window overlaps forbidden range(s): {labels}")

    consumed = [
        entry for entry in freeze.get("consumed", [])
        if _overlap(offset, size, int(entry["offset"]), int(entry["size"]))
    ]
    exact = [
        entry for entry in consumed
        if int(entry["offset"]) == offset and int(entry["size"]) == size
    ]
    if consumed:
        if len(consumed) != 1 or len(exact) != 1:
            raise ValueError(
                "Requested window partially overlaps a consumed confirmation range; "
                "use the exact historical window for reproducibility or choose a fresh disjoint window"
            )
        if not allow_reuse:
            prior = exact[0]
            raise ValueError(
                f"Confirmation window offset={offset} size={size} is already consumed "
                f"({prior.get('label', 'historical confirmation')}); explicit reuse with a reason is required"
            )
        if not reason:
            raise ValueError("Reusing a consumed confirmation window requires a non-empty reason")
        return {
            "action": "reuse",
            "offset": offset,
            "size": size,
            "reason": reason,
            "prior": exact[0],
        }

    if not consume_new:
        raise ValueError(
            "Requested window is currently fresh. Evaluating it consumes a holdout; "
            "explicit consume_new authorization with a reason is required"
        )
    if not reason:
        raise ValueError("Consuming a fresh confirmation window requires a non-empty reason")
    return {
        "action": "consume_new",
        "offset": offset,
        "size": size,
        "reason": reason,
    }


def require_confirmation_reuse(
    offset: int,
    size: int,
    reason: str | None,
    freeze_path: Path | None = None,
) -> dict:
    """Fail closed unless this is an exact, reasoned reproduction of a consumed window."""
    return authorize_confirmation(
        load_freeze(freeze_path),
        int(offset),
        int(size),
        allow_reuse=True,
        reason=reason,
    )


def register_consumption(
    path: Path,
    decision: dict,
    *,
    report: Path,
    config: dict,
    result: dict,
) -> dict:
    """Append a successful fresh-window evaluation to the canonical ledger atomically."""
    if decision.get("action") != "consume_new":
        raise ValueError("Only a consume_new decision can be registered")
    path = Path(path)
    freeze = load_freeze(path)
    authorize_confirmation(
        freeze,
        int(decision["offset"]),
        int(decision["size"]),
        consume_new=True,
        reason=str(decision["reason"]),
    )
    entry = {
        "label": f"confirmation_{decision['offset']}_{decision['offset'] + decision['size']}",
        "offset": int(decision["offset"]),
        "size": int(decision["size"]),
        "status": "consumed",
        "reason": str(decision["reason"]),
        "report": str(report),
        "config_sha256": canonical_sha256(config),
        "result_sha256": canonical_sha256(result),
        "consumed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    freeze["consumed"].append(entry)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return entry
