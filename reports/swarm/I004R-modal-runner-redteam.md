# I004R — Red-team Modal experiment runner before retrieval adoption

## Status

**FOLLOW-UP / do not treat PR #22 as provenance-safe for parallel swarm use yet.**

This was an independent static review of I004 / PR #22. No challenge labels, confirmation window, model inference, or remote Modal compute were consumed.

## Hypothesis

A generic remote runner can remove the >256 MiB Drive-transfer bottleneck, but a subtle Volume/provenance bug would contaminate many later retrieval experiments. The review therefore tested the stronger claim made by PR #22: that runs are reproducible, collision-safe, and bound to exact inputs/code.

## Scope and evidence

Reviewed:
- `modal_experiment.py`
- `modal_experiment_app.py`
- `tests/test_modal_experiment.py`
- `MODAL.md`
- I004 report and PR description
- existing `modal_app.py` and `tools/stage_modal.py` staging conventions
- active I002 stale-cache/provenance work in PR #59

External API semantics were checked against Modal's current official Volume SDK documentation:
https://modal.com/docs/sdk/py/latest/Volume

The docs state that mounted Volumes require explicit `reload()` to see commits made since mount and that Volumes do not provide distributed locking for concurrent writes.

## Findings

### 1. Material: worker does not reload Volume before preflight

`run_registered_experiment()` checks every required path and whether the target run directory already exists immediately after function entry, but never calls `volume.reload()`.

For a reused/warm worker, the mounted filesystem can therefore be older than the latest committed shared Volume state. Consequences:
- a newly staged DB/artifact can be incorrectly reported missing;
- a run directory created by another worker can be invisible;
- the advertised no-overwrite check can operate against stale state.

**Required fix:** call `volume.reload()` before required-path and run-directory checks, while no Volume files are open.

### 2. Material: config hash binds path names, not input contents

The deterministic config hash covers:
- experiment ID;
- module;
- argv;
- required-path strings;
- code SHA;
- branch.

It does **not** cover the contents or semantic version of `project/artifacts/data.duckdb` or any other required input.

If the DuckDB/index is rebuilt or replaced at the same path, identical code and arguments receive the same config hash/default run name despite different data/cache state. This is exactly the type of stale-cache ambiguity identified independently by I006.

**Required fix:** record a stable input/cache fingerprint and include it in run identity. Prefer interoperability with I002 / PR #59 rather than creating a second incompatible fingerprint scheme. A staged manifest is preferable to re-hashing a multi-GB DB for every run if full-file hashing is too expensive.

### 3. Material for parallel swarm use: run-directory collision check is non-atomic

The sequence is:
1. test `out.exists()`;
2. create `out`;
3. write `run.json`;
4. commit Volume.

Two concurrent containers using the same deterministic default run name can both observe the directory absent in their own Volume snapshots and proceed. Modal documents no distributed locking for Volume files. The current code therefore cannot guarantee the PR's “existing run directories are never silently overwritten” property under concurrent launches.

**Required fix:** use collision-proof invocation identity in addition to config identity, an external atomic claim primitive, or explicitly serialize identical run names.

### 4. Secondary: Git provenance is locally exact but not durably recoverable

`_require_clean_git()` proves only that the local worktree is clean. It accepts detached HEAD (`branch == "HEAD"`) and does not ensure the SHA is reachable from a pushed remote branch.

A clean unpushed commit can therefore produce a run whose recorded source cannot be recovered by another swarm agent.

**Suggested fix:** reject detached HEAD and verify the selected commit is reachable from the intended remote branch, or downgrade the documentation from “durable exact branch/SHA provenance” to local provenance.

### 5. Secondary: hard timeout can strand a RUNNING record

The worker commits `status=RUNNING` before launching the subprocess and updates PASS/FAIL only after `subprocess.run()` returns. A hard Modal timeout/container termination can skip the terminal update, leaving the deterministic run directory permanently RUNNING and blocking a default-name retry.

**Suggested fix:** define stale-RUNNING recovery/aborted semantics or use a driver-side finalizer/repair command.

## What passed static review

The following design choices are sound:
- only `ber.*` modules are allowed;
- subprocess execution uses argv, not a shell;
- `..` and absolute required-Volume paths are rejected;
- ordinary nonzero experiment exits are converted to FAIL metadata and raised;
- output directories are isolated by experiment/run name;
- current repo staging paths (`/volume/dataset`, `/volume/project/artifacts/data.duckdb`) match the generic runner's placeholders;
- code/config changes are additive and do not alter selected model behavior.

The existing 4/4 unit-test result from I004 is not disputed. Those tests validate deterministic spec construction and basic parsing, but they do not exercise the shared-Volume concurrency/provenance properties above.

## Baseline / result

Baseline: PR #22 recommendation = **PROMOTE after one authenticated smoke run**.

Red-team result: **FOLLOW-UP before promotion**. Three material invariants are not currently guaranteed:
1. fresh Volume view;
2. exact input snapshot identity;
3. collision-safe parallel run registration.

No competition metric changes.

## Recommendation

Coordinate I004 with I002 / PR #59, add Volume reload + input fingerprinting + collision semantics, then run one authenticated Modal smoke that:
- stages or observes a known input manifest;
- launches the same spec twice;
- demonstrates the intended duplicate policy;
- confirms run.json includes immutable code/config/input provenance;
- exercises a deliberate nonzero exit.

After those checks, I004 is high-value infrastructure because it directly unblocks full-target retrieval experiments that cannot fit through this ChatGPT Drive transfer path.

## Durable review

PR #22 review comment ID: 5320019230  
Issue: #54  
Branch: `agent/i/I004R-modal-runner-redteam`
