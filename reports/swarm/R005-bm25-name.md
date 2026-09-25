# R005 — BM25/IDF-weighted business-name retrieval

## Hypothesis

A source-specific BM25/IDF name-token retrieval channel can recover true S1→S2/S3 links missed by blocker v2 at cap 640 by using broader name-token postings and source-specific document frequency, while keeping marginal candidate growth bounded.

## Change

Prepared `experiments/r005_bm25_name.py`, a full-data streaming experiment harness that:

- reproduces the repository's exact 30,000-anchor development population and SHA256 calibration fold;
- uses the complete train Source 1, Source 2, Source 3, and ground-truth TSVs;
- reproduces blocker-v2 on the same calibration anchors without materializing the repository's full DuckDB database;
- hard-fails unless blocker-v2 exactly matches the committed calibration pair recall and blocking-oracle score;
- evaluates a fixed source-specific BM25 name retriever (k1=1.2, b=0.75, token length >=3, DF cap 5000 per country/source, top 64 per source);
- reports BM25-only, raw baseline+BM25 union, and a fixed RRF cap-640 union;
- reports pair/entity/all-match retrieval recall, blocking-oracle macro F0.5, candidate-count quantiles, country/source slices, marginal recovered positives, runtime, and peak RSS.

No production matcher or inference behavior is changed.

## Protocol

Intended evaluation set: the existing first 30,000 training S1 anchors ordered by `md5('sample517:' || entity_id)`, restricted to the `calibrate` fold using the repository's `fold517:` SHA256 assignment.

Expected calibration anchors: **4,389**.

Target inventory: complete training S2 + S3 records.

Baseline cap: **640**.

The harness asserts the committed blocker-v2 calibration reference before accepting any experimental result:

- candidate pair recall: **0.9458627913066248**
- blocking-oracle macro F0.5: **0.9811781091658961**

The historical confirmation/frozen holdout was **not** consumed.

Exact local/full-data command once a runtime with the complete train files is available:

```bash
PYTHONPATH=src python experiments/r005_bm25_name.py \
  --data-dir /path/to/student_resource/dataset/train \
  --db /tmp/r005.duckdb \
  --out /tmp/r005-result.json
```

The `--download` option exists only for an authorized environment where the supplied Drive files are directly downloadable.

## Baseline

Committed calibration retrieval study, blocker-v2 cap 640:

- entities: **4,389**
- candidate pair recall: **0.9458627913066248**
- candidate entity recall: **0.9454912308973222**
- all-matches-retrieved rate: **0.8411892675852066**
- blocking-oracle macro F0.5: **0.9811781091658961**
- candidate-count p50 / p90 / p99 / max: **597 / 640 / 640 / 640**

These are the comparison targets for R005. The separate confirmation numbers were deliberately not reused for tuning this experiment.

## Result

**BLOCKED — no BM25 metric or score delta is claimed.**

Data access was verified against the shared Drive. The connector listed all four complete training files with these provider sizes:

- `train_source1.tsv`: 210,069,713 bytes
- `train_source2.tsv`: 489,301,488 bytes
- `train_source3.tsv`: 503,705,637 bytes
- `train_ground_truth.tsv`: 127,015,583 bytes

Complete Source 1 and ground truth were successfully transferred into the chat runtime. The live Drive connector rejected Source 2 and Source 3 because each exceeds its 256 MiB raw-transfer ceiling.

The local Python/container backend then independently failed before execution (`ClientError`; Python session creation also returned `TooManyActiveSessionsError`).

A second execution route was attempted through a branch-only GitHub Actions workflow. Pull request #66 produced workflow run 36160380477. Both attempt 1 and an explicit failed-job rerun ended before any step executed: GitHub reported `runner_id=0`, an empty step list, and failure within seconds. Therefore no experiment code ran there either. The temporary workflow was removed from the branch after confirming this was an infrastructure failure.

No sample was substituted. No result was inferred from partial data.

## Error analysis / information gained

The static blocker audit materially narrows what R005 is actually testing. Blocker v2 already gives every matched key an IDF-like contribution `ln(10000001 / freq)` and already retrieves up to four rare eligible name tokens per anchor. Therefore a generic "add IDF" experiment would duplicate existing behavior.

The remaining non-duplicative BM25 hypothesis is specifically:

1. **source-specific frequency** rather than the current combined S2+S3 key frequency;
2. **broader name-token posting lists** beyond the current `freq <= 1000` cutoff;
3. **more than four eligible name tokens** where useful;
4. BM25 document-length / within-name term-frequency normalization;
5. controlled fusion with blocker-v2, including an equal-cap RRF check.

That distinction should be preserved by any recovery agent instead of reimplementing ordinary IDF weighting and declaring novelty.

## Risks

- The new experiment script has not executed in this chat runtime, so it must be treated as an unvalidated handoff until its baseline assertion passes.
- The `--download` path depends on the Drive objects being downloadable in the execution environment; authenticated Drive access may still be required.
- BM25 gains on calibration, if any, need skepticism because wider postings can buy recall simply by adding candidates. The equal-cap RRF result is therefore required alongside the raw union.
- Any tiny positive delta should be replicated on another development slice before promotion.
- Raw challenge rows, predictions, and database artifacts must remain outside Git.

## Recommendation

**BLOCKED / FOLLOW-UP.**

Do not promote R005 based on this run. The useful deliverable is a bounded full-data harness plus a clarified hypothesis that avoids duplicating blocker-v2's existing IDF-like name-token scoring.

Recovery condition: run the committed script in a runtime that already has complete training S2/S3 available (the team's Modal volume or an authorized local/remote machine), require the blocker-v2 assertion to pass, then record the aggregate JSON metrics before making any retrieval decision.
