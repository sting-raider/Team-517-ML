# I001 — Fast fixed-slice benchmark command

## Hypothesis

A single deterministic benchmark command that uses the repository's established development sample and fold assignment will reduce false experiment gains caused by mismatched anchor sets, candidate caps, or accidental evaluation on repeatedly inspected holdout/confirmation data.

## Change

Added `src/ber/benchmark.py` and `tests/test_benchmark.py`.

The benchmark command:

- reproduces the existing source-one sample rule: `ORDER BY md5('sample517:' || entity_id) LIMIT 30000`
- reproduces the existing fold rule: SHA-256 of `fold517:<entity_id>`
- defaults to the calibration fold and cap 640
- refuses development-holdout evaluation unless `--allow-holdout` is supplied explicitly
- runs the current blocker-v2 implementation rather than reimplementing retrieval
- emits JSON with overall, country, and target-source retrieval metrics
- reports pair recall, entity recall, all-matches-retrieved rate, blocking-oracle macro F0.5, candidate count total/mean/p50/p90/p99/max, runtime, candidate cap, index version, and an anchor-selection SHA-256
- records the default baseline reference as `reports/retrieval_study.json:retrieval_640`

No matcher or retrieval behavior was changed.

## Protocol

Tier 0/1 infrastructure validation.

1. Read the current `blocking.py`, `metrics.py`, `experiment.py`, and `retrieval_study.py` from main.
2. Implement the benchmark as a thin wrapper around the existing blocker and official metric implementation.
3. Run five focused unit tests covering deterministic folds, candidate-count statistics, country/source filtering, official retrieval-oracle scoring, and the holdout guard.
4. Independently reproduce the benchmark anchor slice from the complete raw `train_source1.tsv` mounted from the shared Drive.
5. Join that selected slice to the complete raw `train_ground_truth.tsv` and compare aggregate counts with the existing retrieval study.
6. Do not substitute a sample for S2/S3. The current ChatGPT connector rejects `train_source2.tsv` and `train_source3.tsv` because each exceeds its 268,435,456-byte raw-transfer limit, so the full blocker run was not claimed here.

Reference commit for implementation: `36f79706a42a9fdc4e14e15b7275a93a8273e67c`.

## Results

### Tests

All five new benchmark tests passed.

The initial hand-written expected-fold fixture had two incorrect expectations. The deterministic fold implementation disagreed with that fixture; recomputing the established SHA-256 rule showed the implementation was correct and the fixture was wrong. The fixture was corrected and all tests passed. This is precisely the class of quiet split bookkeeping error the benchmark is intended to make harder.

### Real-data slice reproduction

Using the complete raw source-one file:

- source-one rows scanned: **2,206,821**
- deterministic development sample: **30,000**
- fit: **17,990**
- early stopping: **4,570**
- calibration: **4,389**
- development holdout: **3,051**
- calibration US anchors: **2,635**
- calibration India anchors: **1,754**
- source-one streaming/check: **8.47 s**

Using the complete raw ground-truth file on those 4,389 calibration anchors:

- truth rows found: **4,389 / 4,389**
- missing truth rows: **0**
- singleton anchors: **252**
- positive links: **15,276**
- ground-truth streaming/check: **3.37 s**

The **4,389** anchor count and **252** singleton count exactly match the existing `reports/retrieval_study.json` calibration benchmark, validating the new command's default slice selection independently of the cached experiment metadata.

### Existing baseline that the full command must reproduce

For the same calibration slice, current main records blocker-v2 cap-640 metrics of:

- candidate pair recall: **0.9458627913**
- candidate entity recall: **0.9454912309**
- all-matches-retrieved rate: **0.8411892676**
- blocking-oracle macro F0.5: **0.9811781092**
- candidate p50: **597**
- p90 / p99 / max: **640 / 640 / 640**

These are reference values, not new measurements from this I001 run.

No new competition-score delta is claimed.

## Error analysis

The most important observed failure mode was not model behavior but evaluation bookkeeping: manually transcribed fold labels were easy to get wrong. The benchmark centralizes the selection rule and emits a selection hash so experiment outputs can prove they used the same anchors.

The second limitation is environmental. Drive access itself is verified, but this chat runtime cannot transfer the 489 MB and 504 MB S2/S3 TSVs because the connector enforces a 256 MiB raw-file limit. Container networking is unavailable as an alternate downloader. Therefore the end-to-end blocker path could not be exercised here against the full right-side inventory.

## Interpretation

The implementation addresses a real swarm coordination risk: two experiments can otherwise report the same metric name while using different anchor sets, caps, or folds. Centralizing the slice and recording cap/index/selection provenance should make comparisons auditable and reduce false-positive research conclusions.

The independent raw-file check provides strong evidence that the default anchor selection is correct. A single full-data smoke run remains necessary to verify that the SQL/candidate path reproduces the stored blocker-v2 reference metrics exactly.

## Risks

- The end-to-end SQL path was not executed in this ChatGPT runtime because S2/S3 cannot be mounted and DuckDB is not installed locally in this container.
- `retrieval_index_version` records the blocker's version integer but does not hash raw inputs or index contents. Full stale-cache detection is I002 scope.
- Target-source slices intentionally evaluate only truth/candidates from that source; they should not be compared directly with the all-source oracle without that definition in mind.
- The development holdout is merely guarded, not cryptographically inaccessible. The separate confirmation sample remains outside this command.

## Recommendation

**FOLLOW-UP.**

Run the default command once in an environment with the complete existing DuckDB/S2/S3 inventory. If it reproduces `reports/retrieval_study.json:retrieval_640` on the same 4,389 calibration anchors, promote it as the standard swarm retrieval benchmark command. Do not treat this infrastructure change as a model-quality improvement.

## Follow-up tasks

1. Full-data smoke: `python -m ber.benchmark --cap 640`; compare every default metric to `reports/retrieval_study.json:retrieval_640`.
2. I002: add dataset/config/index fingerprints so a benchmark cannot silently reuse stale caches.
3. Have new retrieval experiments call the shared summarization/provenance path rather than creating bespoke evaluation slices.
