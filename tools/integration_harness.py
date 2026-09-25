from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


class IntegrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RefResolution:
    ref: str
    sha: str


@dataclass
class IntegrationResult:
    repository: str
    base: RefResolution
    refs: list[RefResolution]
    command: list[str]
    merge_order: list[str]
    integrated_head: str | None
    tree_sha: str | None
    benchmark_exit_code: int | None
    duration_seconds: float
    status: str
    error: str | None
    worktree: str | None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def _run(cmd: Sequence[str], *, cwd: Path, check: bool = True,
         capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(list(cmd), cwd=str(cwd), text=True,
                          capture_output=capture_output)
    if check and proc.returncode != 0:
        detail = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        raise IntegrationError(
            f"{shlex.join(cmd)} failed: {detail or f'exit code {proc.returncode}'}"
        )
    return proc


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd=repo, check=check)


def resolve_ref(repo: Path, ref: str) -> RefResolution:
    proc = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    return RefResolution(ref=ref, sha=proc.stdout.strip())


def ensure_git_repo(repo: Path) -> None:
    proc = _git(repo, "rev-parse", "--show-toplevel")
    top = Path(proc.stdout.strip()).resolve()
    if top != repo.resolve():
        raise IntegrationError(
            f"repository path must be the git worktree root: expected {top}, got {repo.resolve()}"
        )


def ensure_clean(repo: Path) -> None:
    if _git(repo, "status", "--porcelain").stdout.strip():
        raise IntegrationError("caller repository has uncommitted changes")


def integrate_and_run(repo: Path, base_ref: str, refs: Sequence[str],
                      command: Sequence[str], *, output_json: Path | None = None,
                      keep_worktree: bool = False) -> IntegrationResult:
    started = time.monotonic()
    repo = repo.resolve()
    if not refs:
        raise IntegrationError("at least one experiment ref is required")
    if not command:
        raise IntegrationError("benchmark command must not be empty")

    ensure_git_repo(repo)
    ensure_clean(repo)
    base = resolve_ref(repo, base_ref)
    resolved_refs = [resolve_ref(repo, ref) for ref in refs]

    temp_parent = Path(tempfile.mkdtemp(prefix="team517-integration-"))
    worktree = temp_parent / "worktree"
    result = IntegrationResult(
        repository=str(repo), base=base, refs=resolved_refs,
        command=list(command), merge_order=[r.ref for r in resolved_refs],
        integrated_head=None, tree_sha=None, benchmark_exit_code=None,
        duration_seconds=0.0, status="RUNNING", error=None,
        worktree=str(worktree) if keep_worktree else None,
    )
    worktree_added = False
    try:
        _git(repo, "worktree", "add", "--detach", str(worktree), base.sha)
        worktree_added = True
        _git(worktree, "config", "user.name", "Team 517 Integration Harness")
        _git(worktree, "config", "user.email", "team517-integration@example.invalid")

        for item in resolved_refs:
            merge = _git(worktree, "merge", "--no-edit", "--no-ff",
                         item.sha, check=False)
            if merge.returncode != 0:
                _git(worktree, "merge", "--abort", check=False)
                detail = (merge.stderr or merge.stdout or "").strip()
                raise IntegrationError(
                    f"merge conflict/failure for {item.ref} ({item.sha}): {detail}"
                )

        result.integrated_head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
        result.tree_sha = _git(worktree, "rev-parse", "HEAD^{tree}").stdout.strip()
        bench = _run(command, cwd=worktree, check=False, capture_output=False)
        result.benchmark_exit_code = bench.returncode
        result.status = "PASS" if bench.returncode == 0 else "FAIL"
    except Exception as exc:
        result.status = "ERROR"
        result.error = str(exc)
        raise
    finally:
        result.duration_seconds = round(time.monotonic() - started, 6)
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(result.to_json() + "\n", encoding="utf-8")
        if worktree_added and not keep_worktree:
            _git(repo, "worktree", "remove", "--force", str(worktree), check=False)
        if not keep_worktree:
            shutil.rmtree(temp_parent, ignore_errors=True)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine experiment refs in a disposable worktree and run one exact command."
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--ref", action="append", dest="refs", required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--keep-worktree", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("benchmark command is required after --")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = integrate_and_run(
            args.repo, args.base, args.refs, args.command,
            output_json=args.output_json, keep_worktree=args.keep_worktree,
        )
    except IntegrationError as exc:
        print(f"integration harness error: {exc}", file=os.sys.stderr)
        return 2
    print(result.to_json())
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
