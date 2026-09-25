# I009 — Stage runtime and memory profiler

## Hypothesis

The current inference path exposes only coarse elapsed/blocking/scoring-export console timing. A lightweight stage profiler can make retrieval widening and compute/resource choices evidence-based without changing candidate membership, model probabilities, thresholds, or official outputs.

## Change

Added `src/ber/profiling.py` with an opt-in `StageProfiler` that records:

- repeated-call count
- total wall seconds
- max single-call seconds
- best-effort current RSS before/after
- process peak RSS
- compact JSON output via atomic replace

Instrumented `ber.predict` at these boundaries when `profile_path` / `--profile` is provided:

- `build_index`
- `candidate_retrieval`
- `score_batch`
- nested `model_predict`
- `shard_export`
- `executor_shutdown`
- `final_merge`

The Modal `score_test` path now writes `<run>/profile.json` automatically.

No retrieval, feature, CatBoost, threshold, shortlist, hashing, or TSV membership logic was intentionally changed.

## Protocol

Tier 0/1 infrastructure validation only.

Base commit: `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`

Branch: `agent/i/I009-stage-profiler`

Focused synthetic validation was executed in the available container runtime using the exact profiler/test logic copied from the branch:

```
PYTHONPATH=/tmp/i009 python -m unittest discover -s /tmp/i009/tests -v
```

Result: 2/2 tests passed. The tests cover repeated-stage aggregation, deterministic synthetic timing/RSS observations, and atomic JSON emission.

The notebook Python backend could not start because the environment reported `TooManyActiveSessionsError`, so no claim is made that the repository's full test suite was executed in this chat.

No confirmation/frozen holdout was consumed. No raw challenge rows were copied into Git. Drive access was verified, but this task does not require S2/S3 transfer or an empirical model rerun.

## Baseline

Current main exposes coarse inference timing in `src/ber/predict.py`: per chunk, one retrieval/blocking duration and a combined scoring/export remainder. It does not persist a machine-readable breakdown for model inference, shard serialization/checksums, executor shutdown, or final merge.

Competition baseline remains unchanged and is not re-evaluated here:

- confirmation macro F0.5: 0.928835
- cap-640 candidate pair recall: 0.947246
- blocking-oracle macro F0.5: 0.980951

These are context only, not results of I009.

## Results

| Check | Result |
|---|---|
| Synthetic profiler aggregation | PASS |
| Atomic JSON write | PASS |
| New external dependency | none |
| Default local `ber.predict` behavior | profiler disabled unless `--profile` is supplied |
| Modal score path | profiler enabled; writes `profile.json` |
| Official macro F0.5 delta | not measured / expected 0 by construction |
| Candidate recall delta | not measured / expected 0 by construction |

No actual stage bottleneck ranking is claimed yet. A full or bounded real scoring run is required for that measurement.

## Error analysis

The main risks are measurement rather than modeling risks:

1. `score_batch` includes feature construction, multiprocessing wait time, Python bookkeeping, and model inference. Nested `model_predict` lets the remainder be derived, but it is not a direct worker-process CPU profile.
2. Parent-process RSS does not include a precise sum of all worker RSS. Peak RSS is therefore useful for regressions on the parent process, not a complete cluster/container memory accounting.
3. `resource.ru_maxrss` semantics differ by platform; the helper normalizes Linux KiB and macOS bytes.
4. `/proc/self/statm` is Linux-specific. Unsupported platforms return null current RSS rather than fabricating a value.
5. Instrumentation overhead is small context-manager/time/RSS sampling work, but has not yet been benchmarked on the full scorer.

## Risks

- No leakage or label access is introduced.
- No record IDs are added as predictive features.
- No external entity/business data is used.
- No model/retrieval semantics are intentionally modified.
- A real Modal smoke/full run is still needed to verify profile emission and quantify overhead/bottlenecks under production multiprocessing.

## Recommendation

**FOLLOW-UP**

Keep the profiler code as an additive instrumentation candidate, then run one normal Modal scoring partition with the branch and inspect `profile.json`. Promote it as standard experiment telemetry if output is valid and overhead is negligible. The first useful decision from that run should be whether effort belongs in blocker SQL/indexing, feature construction/multiprocessing, CatBoost inference, or output serialization/merge.

## Follow-up tasks

- Run one representative Modal partition with profiling enabled and record stage shares + peak RSS.
- If `score_batch - model_predict` dominates, profile feature-worker wait/serialization more deeply.
- If `candidate_retrieval` dominates, use the result to size R002/R014-style wider retrieval experiments and Modal CPU/memory requests.
