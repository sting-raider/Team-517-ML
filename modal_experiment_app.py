"""Generic Modal runner for full-data Team 517 swarm experiments.

Run this from an experiment branch. The launcher refuses dirty worktrees so the
Modal image can be tied to an exact Git commit. Challenge data and experiment
outputs remain in the private team517-business-er Volume.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import modal

from modal_experiment import (
    build_spec,
    command_for_spec,
    parse_args_json,
    parse_required_paths_json,
    run_directory,
)

ROOT = Path(__file__).parent
VOLUME_NAME = "team517-business-er"
VOLUME_ROOT = Path("/volume")
SCRATCH = Path("/tmp/team517-experiment")

app = modal.App("team517-swarm-experiments")
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("g++", "git")
    .pip_install_from_requirements(str(ROOT / "requirements.txt"))
    .env({"PYTHONPATH": "/app/src:/app", "PYTHONUNBUFFERED": "1"})
    .add_local_dir(str(ROOT / "src"), "/app/src")
    .add_local_file(str(ROOT / "modal_experiment.py"), "/app/modal_experiment.py")
)


def _write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


@app.function(
    image=image,
    volumes={str(VOLUME_ROOT): volume},
    cpu=8,
    memory=32768,
    timeout=4 * 60 * 60,
)
def run_registered_experiment(
    experiment_id: str,
    module: str,
    args_json: str,
    required_paths_json: str,
    code_sha: str,
    branch: str,
    run_name: str = "",
):
    """Execute one ber.* module against private Volume data with provenance."""
    import os
    import time
    from datetime import datetime, timezone

    spec = build_spec(
        experiment_id=experiment_id,
        module=module,
        args=parse_args_json(args_json),
        required_paths=parse_required_paths_json(required_paths_json),
        code_sha=code_sha,
        branch=branch,
        run_name=run_name or None,
    )
    missing = [rel for rel in spec["required_paths"] if not (VOLUME_ROOT / rel).exists()]
    if missing:
        raise FileNotFoundError(f"Missing required Modal Volume inputs: {missing}")

    out = run_directory(VOLUME_ROOT, spec)
    if out.exists():
        raise FileExistsError(
            f"Experiment output already exists: {out}. Use a new --run-name instead of overwriting provenance."
        )
    out.mkdir(parents=True, exist_ok=False)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    command = command_for_spec(spec, volume_root=VOLUME_ROOT, run_dir=out)
    started = datetime.now(timezone.utc)
    metadata = {
        **spec,
        "status": "RUNNING",
        "started_at": started.isoformat(),
        "command": command,
        "runtime": {"cpu": 8, "memory_mib": 32768, "timeout_seconds": 4 * 60 * 60},
        "paths": {
            "volume_root": str(VOLUME_ROOT),
            "run_dir": str(out),
            "database": str(VOLUME_ROOT / "project/artifacts/data.duckdb"),
            "dataset": str(VOLUME_ROOT / "dataset"),
        },
    }
    _write_json(out / "run.json", metadata)
    volume.commit()

    env = os.environ.copy()
    env.update(
        {
            "TEAM517_EXPERIMENT_ID": spec["experiment_id"],
            "TEAM517_CONFIG_HASH": spec["config_hash"],
            "TEAM517_CODE_SHA": spec["code_sha"],
            "TEAM517_BRANCH": spec["branch"],
            "TEAM517_VOLUME_ROOT": str(VOLUME_ROOT),
            "TEAM517_RUN_DIR": str(out),
            "TEAM517_DB": str(VOLUME_ROOT / "project/artifacts/data.duckdb"),
            "TEAM517_DATASET_ROOT": str(VOLUME_ROOT / "dataset"),
        }
    )
    start_clock = time.monotonic()
    completed = subprocess.run(command, cwd=SCRATCH, env=env, check=False)
    finished = datetime.now(timezone.utc)
    metadata.update(
        {
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "finished_at": finished.isoformat(),
            "duration_seconds": round(time.monotonic() - start_clock, 3),
            "returncode": completed.returncode,
        }
    )
    _write_json(out / "run.json", metadata)
    volume.commit()
    if completed.returncode != 0:
        raise RuntimeError(
            f"Experiment command failed with exit code {completed.returncode}; metadata: {out / 'run.json'}"
        )
    return metadata


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _require_clean_git() -> tuple[str, str]:
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if dirty.strip():
        raise RuntimeError("Commit or stash the working tree before a Modal experiment; provenance requires exact code.")
    return _git_output("rev-parse", "HEAD"), _git_output("rev-parse", "--abbrev-ref", "HEAD")


@app.local_entrypoint()
def main(
    experiment_id: str,
    module: str,
    args_json: str = "[]",
    required_paths_json: str = '["project/artifacts/data.duckdb"]',
    run_name: str = "",
    dry_run: bool = False,
):
    code_sha, branch = _require_clean_git()
    spec = build_spec(
        experiment_id=experiment_id,
        module=module,
        args=parse_args_json(args_json),
        required_paths=parse_required_paths_json(required_paths_json),
        code_sha=code_sha,
        branch=branch,
        run_name=run_name or None,
    )
    if dry_run:
        out = run_directory(VOLUME_ROOT, spec)
        preview = {
            **spec,
            "command": command_for_spec(spec, volume_root=VOLUME_ROOT, run_dir=out),
            "run_dir": str(out),
        }
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return
    result = run_registered_experiment.remote(
        experiment_id=experiment_id,
        module=module,
        args_json=args_json,
        required_paths_json=required_paths_json,
        code_sha=code_sha,
        branch=branch,
        run_name=run_name,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
