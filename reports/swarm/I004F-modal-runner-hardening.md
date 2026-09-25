# I004F — Harden Modal swarm runner after red-team findings

## Hypothesis

The generic Modal swarm runner from I004 can safely unblock full-data retrieval and
matcher experiments only if its Volume view, input provenance, and concurrent run
identity are trustworthy. Closing the three concrete I004R findings should remove
those failure modes without changing any retrieval, matcher, metric, or submission
behavior.

## Change

This task recovered I004 from PR #22 at head
`f4f0646380fe0b9764774b4658a0a58df9a72368` instead of building a second runner.

The hardening adds:

1. **Fresh Volume view before reads.** `run_registered_experiment()` calls
   `volume.reload()` before required-input existence checks, fingerprints, or run
   directory construction.
2. **Actual input snapshot provenance.** Required files are identified by size plus
   SHA-256 over first/middle/last 64 KiB samples. Required directories recursively
   fingerprint contained files. The deterministic `run_identity_hash` combines the
   original config hash with this observed input fingerprint.
3. **Collision-resistant immutable attempts.** Every launch receives a random
   20-hex invocation ID and writes beneath
   `<experiment>/<run-name>/<run-identity>/<invocation-id>/`. Two workers with the
   same logical config/input therefore do not race to create or overwrite one shared
   run record.
4. **Retry preservation.** A stranded `RUNNING` attempt remains visible while a
   retry gets a new invocation directory. Ordinary launcher exceptions after
   directory creation are checkpointed as `ERROR` when possible.
5. **Reviewable Git provenance.** Local launch now rejects detached HEAD as well as a
   dirty working tree.
6. **Expanded metadata/env.** `run.json` and experiment environment include
   `input_fingerprint`, `run_identity_hash`, and `invocation_id`.

No competition model, blocker, feature, threshold, metric, or candidate logic changed.

## Protocol

Tier: **0/1 infrastructure validation**.

Issue: #75.

Branch: `agent/i/I004F-modal-runner-hardening`.

Recovered base: I004 PR #22 head
`f4f0646380fe0b9764774b4658a0a58df9a72368`.

Red-team input: I004R / Issue #54 and its PR #22 review, which identified three
blocking concerns: stale mounted-Volume reads, path-only input identity, and a
same-run TOCTOU collision.

No challenge confirmation/frozen holdout was consumed. No challenge row was needed
for validation.

Local validation:

```text
cd /mnt/data/i004f
PYTHONPATH=/mnt/data/i004f python -m unittest -v tests/test_modal_experiment.py
python -m py_compile modal_experiment.py modal_experiment_app.py tests/test_modal_experiment.py
```

The focused tests cover deterministic config identity, safe module/path parsing,
sampled content signatures, input-snapshot identity changes, unique invocation
directories, and the ordering requirement that `volume.reload()` precedes Volume
preflight/fingerprinting.

This ChatGPT runtime has GitHub, Drive and local Python/container execution, but no
authenticated Modal execution connector/CLI. Therefore no remote Modal run is
claimed.

## Baseline

I004 originally reported 4/4 focused tests and a deterministic dry run. I004R then
found three material reproducibility/concurrency gaps:

- a warm worker could inspect a stale mounted Volume before preflight;
- the config hash described required *path strings* but not the actual files at
  those paths;
- two identical concurrent launches could race against one shared run directory.

Those findings changed I004's effective recommendation from PROMOTE to FOLLOW-UP
pending hardening and a real smoke run.

## Results

| Check | I004 baseline | I004F |
|---|---|---|
| Focused local tests | 4/4 pass | **8/8 pass** |
| Test runtime | <1 s | **0.005 s** |
| Python syntax compilation | pass | **pass** |
| Reload before Volume reads | not enforced | **enforced + regression-guarded** |
| Actual required-input identity | path strings only | **sampled content fingerprint** |
| Same-config concurrent attempts | shared run path | **unique immutable invocation paths** |
| Stranded RUNNING retry | blocked by shared path | **new invocation can retry** |
| Detached HEAD | accepted | **rejected** |

No official macro F0.5, pair recall, blocking oracle, singleton rate, or country
metric changed or was rerun. This is infrastructure work.

## Error analysis

The three red-team blockers now have explicit source-level mitigations:

- **Stale mount:** reload happens before both existence checks and signatures.
- **Stale input under same pathname:** changing sampled input content changes the
  input fingerprint and therefore the deterministic run identity.
- **Same logical run collision:** invocation IDs produce disjoint file paths, so
  competing workers no longer write the same `run.json`.

The test suite additionally demonstrates that two byte-identical copies produce the
same sampled signature, a changed middle region changes it, and 64 generated
invocation IDs/directories are distinct in the deterministic test.

## Interpretation

The fix converts `run_name` from an unsafe shared write target into a human label
above two explicit identities:

- configuration identity: code + args + declared inputs;
- input identity: observed required-input snapshot.

An immutable per-invocation leaf then records the actual attempt. This preserves
comparability without pretending two retries are the same execution.

The change is deliberately self-contained in the standard-library runner helper.
It does not import I002's still-unmerged provenance module, but uses the same cheap
sampled-file-signature idea so the contracts can be unified later without changing
the scientific meaning.

## Risks

1. **Sampled signatures are not full content hashes.** A mutation outside the
   first/middle/last sampled regions can theoretically be missed. This is an
   accidental-staleness guard, not adversarial authentication.
2. **Large required directories can make recursive fingerprinting expensive.**
   Experiments should declare the narrowest actual inputs rather than the entire
   Volume.
3. **No authenticated Modal smoke was possible here.** The source contract and local
   tests pass, but Modal API/runtime behavior still needs one real read-only or tiny
   experiment invocation before the runner is treated as fully promoted.
4. **Hard worker termination can still leave RUNNING metadata.** The new immutable
   retry model prevents that record from being overwritten or blocking another
   attempt; it does not magically execute a finally block after the container dies.
5. **Remote reachability of the Git commit is recorded, not proven.** Detached HEAD is
   rejected, but the launcher does not currently verify the branch/SHA against
   GitHub before launch.

## Recommendation

**FOLLOW-UP**, with the three I004R source-level blockers closed.

The remaining promotion gate is one authenticated Modal smoke against the private
`team517-business-er` Volume. If it confirms reload visibility, required-input
fingerprinting, run metadata persistence, and a successful tiny `ber.*` execution,
promote the runner and use it to recover the full-data retrieval experiments blocked
by the 256 MiB Drive handoff ceiling.

## Follow-up tasks

1. Run one authenticated tiny/read-only Modal experiment and preserve its
   `run.json`.
2. After that smoke, recover a blocked P0 retrieval task such as R001/R002/R003 on
   the full S2/S3 inventory.
3. If I002 is promoted, consolidate the duplicated sampled-file-signature helper
   behind one provenance utility without changing stored identity semantics.
