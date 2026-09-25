# R002 — Character 3–5 gram name retriever over blocker v2

## Status

**BLOCKED / FOLLOW-UP**. No retrieval metric or score gain is claimed.

## Hypothesis

A country/source-aware character 3–5 gram business-name retrieval channel may recover true S1→S2/S3 links missed by blocker v2 at cap 640, especially under spelling, spacing, abbreviation, and transliteration corruption, without an unacceptable marginal candidate burden.

## Intended protocol

The experiment was scoped to the established deterministic development sample and calibration fold used by `reports/retrieval_study.json`.

Required comparison on exactly the same anchors:

- blocker v2 at cap 640;
- blocker v2 union character-name candidates;
- pair recall;
- entity recall;
- all-matches-retrieved rate;
- blocking-oracle macro F0.5;
- candidate-count mean/p50/p90/p99/max;
- US/India and S2/S3 slices;
- marginal true positives recovered per added candidate;
- runtime and memory.

No matcher retuning or confirmation/final-holdout tuning was planned.

## Data access verification

The shared Google Drive dataset is accessible from this ChatGPT environment.

Complete files successfully exposed through the Drive connector:

- `train_source1.tsv`: 210,069,713 bytes;
- `train_ground_truth.tsv`: 127,015,583 bytes.

The two target inventories required for a valid retrieval experiment exceed the connector's raw-download ceiling:

- `train_source2.tsv`: **489,301,488 bytes**;
- `train_source3.tsv`: **503,705,637 bytes**;
- connector ceiling observed: **268,435,456 bytes** per raw file.

The container cannot fetch the Drive URLs directly because it does not inherit the connector's Drive authentication/network path. No lossless sub-256 MiB S2/S3 shard set was available on the Project file surface during this run.

## Why no sampled substitute was used

Retrieval posting frequencies, candidate ranks, cap saturation, and the blocker oracle depend on the complete S2/S3 target inventory. Sampling either target source would change those quantities and make comparison with the existing cap-640 baseline invalid.

Accordingly:

- no sampled target inventory was substituted;
- no partial blocker baseline was presented as comparable;
- no R002 pair/entity/oracle metric was fabricated;
- no code was promoted based on unmeasured retrieval behavior.

## Baseline reference

Existing repository result used only as context, not re-measured here:

- candidate pair recall @640: **0.947246**;
- blocking-oracle macro F0.5: **0.980951**.

R002 must first reproduce those values on the exact same calibration anchors before any character-retriever delta is interpreted.

## Handoff

Recover this task on a runtime with complete S2/S3 access, preferably the private Modal/shared-volume path once that runner has passed its own provenance smoke.

Suggested next steps:

1. materialize the exact established calibration anchors;
2. reproduce blocker-v2 cap-640 metrics exactly;
3. build country-partitioned character 3/4/5-gram posting lists over normalized names;
4. measure raw union fanout before pruning;
5. test bounded per-channel top-k or IDF-weighted gram scoring if raw fanout is excessive;
6. report marginal recovered positives and candidate cost on the identical anchor universe.

## Compliance

Only supplied challenge files/metadata were accessed. No external business identity data was used. No raw challenge rows, predictions, caches, models, or embeddings are committed.
