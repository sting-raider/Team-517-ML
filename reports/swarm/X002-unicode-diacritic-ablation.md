# X002 — Unicode/diacritic normalization ablation

**Issue:** #101  
**Pod:** X (France/generalization)  
**Branch:** `agent/x/X002-unicode-diacritic-ablation`  
**Recommendation:** **BLOCKED**

## Hypothesis

The current folded-only text representation may discard discriminative Unicode/diacritic structure that is much more prevalent in unseen-France records. A Unicode-preserving normalized view, used in parallel with the current accent-folded view, could retain current recall behavior while adding a precision/generalization signal.

## Change

No production code was changed. This run attempted to execute the full Source-1 ablation on the complete supplied files and deliberately stopped rather than substitute a sample or claim metrics from another agent's experiment.

## Protocol / capability check

Live GitHub and Google Drive access were verified. The shared Drive exposed the complete challenge dataset.

Successfully materialized before the execution backend failed:

- `train_source1.tsv`: 210,069,713 bytes
- `test_source1.tsv`: 175,022,086 bytes
- `train_ground_truth.tsv`: 127,015,583 bytes

The production normalizer on current `main` was inspected directly:

```sql
trim(regexp_replace(lower(strip_accents(coalesce(s, ''))), '[^\\p{L}\\p{N}]+', ' ', 'g'))
```

The blocker consumes only the folded `n` / `a` columns. The selected 47-feature matcher also receives only those normalized strings for all name/address comparison features.

The intended full-file analysis was: country/split percent changed, distinct-key loss, collision-row inflation, fanout quantiles, and collision groups created solely by folding, with no France labels invented.

## Existing baseline evidence

This task was intentionally checked against live swarm work before execution.

X001 and the independent X007 replication already establish on complete Source-1 files that France has materially more diacritic structure than labeled countries. X007 reports, among other diagnostics:

- France test S1 name accent-fold changed: 15.721%
- France test S1 address accent-fold changed: 27.831%
- France address accent-only collision-key rows: 0.503%
- France full-normalization address collision-key rows: 0.829%
- full-normalization name collision-row rate: US 7.613%, India 1.583%, France 1.536%

Those are Source-1 format diagnostics, not French accuracy or candidate-recall estimates. X002 was meant to extend them into a controlled parallel-view ablation rather than repeat the census.

## Blocker encountered

After the raw files were successfully transferred into the ChatGPT analysis workspace, all available execution backends began failing at process start with a session-level `ClientError`, including:

- a one-line container `echo`
- a one-line Python runtime check
- a one-line user-visible Python runtime check

No analysis process actually started after the failure.

Separately, direct Drive transfer of `train_source2.tsv` (489,301,488 bytes) fails with HTTP 413 because the live connector caps raw downloads at 268,435,456 bytes. The same structural limit applies to the roughly 504 MB train Source-3 file. Therefore this session cannot evaluate pair-level Unicode views or official macro F0.5 without a working remote/full-data execution path.

## Results

No new competition metric is claimed.

- official macro F0.5: **not measured**
- candidate recall/oracle: **not measured**
- France accuracy: **not measurable because France has no labels**
- new Source-1 ablation metrics: **not measured in this run because the execution backend failed before processing**

This is a capability BLOCKED result, not a scientific rejection of X002.

## Red-team / integrity

- No sample was substituted for the promised full-file run.
- No external business/entity data were used.
- No France labels or pseudo-labels were invented.
- No confirmation/frozen holdout was consumed.
- Existing X001/X007 aggregate results are treated as prior evidence, not re-labeled as measurements from this run.
- No production behavior was changed without same-slice scoring evidence.

## Recommendation

**BLOCKED / RELEASED.**

Do not infer that a Unicode-preserving parallel view is useless. The live evidence still supports testing it. Execute X002 when either:

1. the chat execution backend can process the already-accessible Source-1 files and a full-target path exists, or
2. the private Modal volume / lossless shards provide complete S2/S3 access.

The decisive next benchmark should keep the existing folded view, add a Unicode-preserving parallel view, and compare on identical labeled US/India development anchors plus country-transfer stress. It must report official macro F0.5, retrieval recall/oracle if retrieval changes, and candidate-count effects.

This issue lease is released so another capable agent can recover it rather than waiting on this session.
