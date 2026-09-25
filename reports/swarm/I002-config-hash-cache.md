# I002 — Config hashing and stale-cache detection

## Recommendation

**FOLLOW-UP** before merge: run one tiny DuckDB integration smoke in the normal repository/Modal environment and measure the full-table fingerprint startup cost. The pure-Python provenance contract and all modified Python sources pass the checks available in this ChatGPT runtime, but this container has no DuckDB installation and outbound package installation is blocked.

This task changes experiment integrity/invalidation behavior only. It does **not** claim an official macro F0.5 improvement.

## Hypothesis

Parallel swarm experiments can produce false gains if a retrieval index, pair-feature matrix, tuned CatBoost trial, or resumable inference shard is silently reused after its behavior-relevant inputs changed. Deterministic code/config/data fingerprints should make those mismatches fail closed rather than look like valid experiment results.

## Baseline / motivation

The selected main-branch baseline is still the depth-10 CatBoost system with independent confirmation macro F0.5 **0.928835**. That number is a reference only; I002 did not rerun or change it.

The main branch previously had several weak reuse boundaries:

- blocker indexes were trusted when `index_versions.version == 2`;
- `ber.experiment` reused `features.npz` whenever the file existed and `--refresh` was absent;
- `ber.wide_evaluate` likewise reused a wide feature cache by existence;
- `ber.tune` skipped completed depth trials when report/model/probability files existed;
- inference `run.json` recorded a hard-coded `index_version: 2`, not the actual blocker/feature/shortlist implementation or indexed record inventory;
- `ber.data` reused a prepared `train`/`test` table solely because sources 1/2/3 were present, without proving those rows came from the current raw TSVs or preprocessing code.

I006 independently identified stale-cache provenance as a high research-integrity risk; I002 is the bounded implementation response.

## Exact change

### `src/ber/provenance.py`

Added deterministic provenance helpers:

- canonical JSON + SHA256 config fingerprints;
- complete source-file SHA256 fingerprints;
- lightweight large-file signatures using file size plus first/middle/last 64 KiB samples;
- checksummed compatibility sidecars that fail closed when missing, malformed, tampered, or mismatched;
- order-independent DuckDB relation fingerprints using row count + `bit_xor(hash(...))` + 128-bit `sum(hash(...))`;
- identifier validation so relation names/columns cannot be interpolated unsafely.

The file signature is intentionally a cheap accidental-staleness guard, not an adversarial whole-file hash.

### `src/ber/data.py`

Prepared DuckDB split reuse is now bound to:

- sampled signatures of all three raw TSVs for that split;
- an explicit data-preparation version;
- the exact normalization macro SQL;
- the exact source-loading implementation.

A new `data_input_signatures` table records the intended split identity before source import. This permits safe source-by-source resume after an interrupted signed import, but an unsigned legacy table or a changed raw/preprocessing signature fails closed. `--refresh` is required to rebuild such a table explicitly. The audit report now records the prepared-input fingerprints.

### `src/ber/blocking.py`

Retrieval index reuse is now bound to:

- blocker/index implementation source;
- explicit index version and maximum key frequency;
- the exact rowid-backed split inventory: `rowid, entity_id, country, source, n, a`.

The database stores the resulting fingerprint in a new `index_signatures` table. A matching signed index is reused. A changed signature rebuilds. A pre-I002 version-2 index with no signature is rebuilt once rather than trusted.

`build_index` returns the compatibility fingerprint so downstream inference can bind resumable outputs to the same exact index identity.

### `src/ber/predict.py`

The resumable `run.json` identity now includes:

- model SHA256 and saved model config;
- candidate cap / batching / partition parameters;
- actual retrieval-index compatibility fingerprint;
- blocker implementation fingerprint;
- complete `features.py` source hash;
- complete `shortlist.py` source hash;
- complete prediction module source hash.

Changing any of those prevents old output shards from being silently resumed under a different inference contract.

### `src/ber/experiment.py`

New `features.manifest.json` sidecar binds a materialized pair-feature cache to:

- feature cache schema version;
- ordered `FEATURE_NAMES`;
- complete feature implementation source hash;
- full normalized training relation including physical `rowid`;
- full truth relation;
- selected anchor relation;
- candidate relation including retrieval score and hit count.

A legacy/mismatched pair-feature cache now raises instead of silently loading. `--refresh` remains the explicit rebuild path.

### `src/ber/wide_evaluate.py`

The calibration anchor relation is deterministically recreated first. Existing `artifacts/wide_calibration/features.npz` is reused only when its compatibility manifest matches the current database/code/candidate state.

### `src/ber/tune.py`

Depth-8/depth-10 trial reuse now requires:

- signed baseline and wide feature caches;
- trial hyperparameter identity;
- sampled signatures of both feature arrays, anchor metadata, and their manifests;
- a matching per-trial manifest.

Added `--refresh` to explicitly retrain completed trials. Unsigned legacy feature/trial caches do not silently pass.

## Validation

Executed in the current ChatGPT container:

```text
PYTHONPATH=/mnt/data/i002/src python -m unittest -v \
  /mnt/data/i002/tests/test_provenance.py \
  /mnt/data/i002/tests/test_data_provenance.py
```

Result: **8/8 tests passed** in approximately **0.010 s**.

Covered:

1. canonical config hash is independent of dictionary insertion order;
2. source-file hash matches the implementing module bytes;
3. sampled file signature is copy-stable and detects a changed middle region;
4. manifest rejects changed config and manifest tampering;
5. missing manifest fails closed;
6. relation fingerprint contract includes count/XOR/sum and rejects unsafe identifiers;
7. prepared split identity is deterministic for unchanged raw inputs;
8. mutating one raw source changes only the expected source signature and the split identity.

The exact fetched branch sources for the changed integration modules were also syntax-compiled locally:

```text
python -m py_compile \
  src/ber/provenance.py src/ber/data.py src/ber/blocking.py src/ber/predict.py \
  src/ber/experiment.py src/ber/tune.py src/ber/wide_evaluate.py \
  tests/test_provenance.py tests/test_data_provenance.py
```

Result: **PASS**.

The container does not have DuckDB installed. An attempted `pip install duckdb==1.5.5` failed because outbound DNS/package access is disabled, so the actual DuckDB relation query and rebuild/reuse path were **not** executed here. DuckDB's current documentation exposes both `bit_xor` and the table `rowid` pseudocolumn used by the implementation, but documentation is not a substitute for the required repository-environment smoke test.

## Metrics

No challenge metric was consumed or changed.

| Metric | Baseline reference | I002 |
|---|---:|---:|
| independent confirmation macro F0.5 | 0.928835 | not rerun |
| candidate pair recall @640 | 0.947246 | not rerun |
| blocking-oracle macro F0.5 | 0.980951 | not rerun |
| provenance unit tests | n/a | 8/8 pass |
| changed Python files syntax compile | n/a | pass |

## Runtime / resource impact

Measured pure-Python tests are negligible (~0.010 s). The new DuckDB compatibility checks scan behavior-relevant relations before cache reuse. Their full-data wall time and memory cost were **not measured** in this runtime and must be measured in the follow-up smoke.

The sampled large-file signature reads at most three 64 KiB regions per file.

## Error analysis / red-team checks

The implementation specifically closes these false-gain modes:

- raw split TSV/preprocessing changes while an old prepared DuckDB table remains;
- blocker code changes without manually incrementing an integer version;
- database record/reordering changes while an old rowid-based index remains;
- candidate-table changes with an old pair-feature matrix present;
- feature implementation changes while `FEATURE_NAMES` stay unchanged;
- truth changes with an old labeled feature matrix present;
- CatBoost tuning input/hyperparameter changes with old trial artifacts present;
- feature/shortlist/prediction code changes while resumable output shards remain.

Known remaining risks:

1. The sampled large-file signature can theoretically miss a mutation outside the sampled regions. It is designed for accidental cache mismatch detection, not hostile tampering.
2. Semantic embedding/`records.parquet` cache provenance is outside this selected-baseline patch and should be tightened before semantic models are promoted.
3. Full-table fingerprint overhead is unknown until a normal DuckDB/Modal smoke is run.
4. Existing pre-I002 prepared databases are intentionally treated as unsigned. Adoption therefore requires an explicit `ber.data --refresh` rebuild once; this migration cost must be planned rather than hidden.

## Required follow-up

On a machine/Modal volume with the repository's pinned DuckDB:

1. create tiny raw train/test TSVs, prepare them once, and confirm a second run reuses the signed split tables;
2. mutate one raw source and confirm `ber.data` refuses reuse without `--refresh`, then confirm explicit refresh rebuilds it;
3. create a tiny synthetic DuckDB containing `train`, `truth`, anchors, and candidates;
4. materialize features once and confirm the second run reuses the signed cache;
5. mutate one candidate row and confirm feature-cache reuse fails;
6. build an index twice and confirm the second call reuses it;
7. mutate/recreate the split inventory and confirm the index rebuilds;
8. record prepared-input signature and full-table relation-fingerprint wall time on the real dataset.

If those pass with acceptable startup overhead, **PROMOTE** I002. Otherwise optimize the relation signature implementation without weakening the fail-closed contract.

## Compliance

No challenge row content, predictions, models, embeddings, or raw data are committed. No external business identity data is used. Record IDs are used only for cache/inventory identity and are not added as predictive model features.
