# R008 — Reverse S2/S3→S1 retrieval propagation

## Hypothesis
Reverse retrieval from target records (S2/S3) into Source 1 may recover true links missed by the current forward blocker under source-asymmetric corruption and one-to-many matching.

## Change
No production retrieval change was made. The task stopped before implementation because the complete target-source inventories could not be materialized in this ChatGPT runtime, and a sampled target inventory would not support the required same-slice blocker comparison.

## Protocol
- Repository baseline: `main` at claim time, branch `agent/r/R008-reverse-retrieval`.
- Intended evaluation: established deterministic 30k development population, calibration fold only (4,389 anchors), blocker-v2 cap 640.
- Required files from the shared Drive:
  - `train_source1.tsv`: 210,069,713 bytes — successfully materialized to the analysis runtime.
  - `train_ground_truth.tsv`: 127,015,583 bytes — successfully materialized.
  - `train_source2.tsv`: 489,301,488 bytes — raw transfer rejected.
  - `train_source3.tsv`: 503,705,637 bytes — raw transfer rejected.
- Live Drive connector error for both target files: HTTP 413, file exceeds the 268,435,456-byte transfer limit.
- No confirmation/frozen holdout was read or consumed.
- No external business/entity data was used.

## Baseline
Committed calibration blocker-v2 cap-640 baseline from `reports/retrieval_study.json`:
- candidate pair recall: 0.9458627913
- candidate entity recall: 0.9454912309
- all-matches-retrieved rate: 0.8411892676
- blocking-oracle macro F0.5: 0.9811781092
- candidate count p50/p90/p99/max: 597 / 640 / 640 / 640

These are reference aggregates only; they were not re-measured in this blocked run.

## Result
**BLOCKED.** The experiment requires the complete S2 and S3 retrieval inventory to preserve baseline parity and candidate-cap semantics. The live Drive raw-file transfer path rejects both files above 256 MiB. No sample result is reported because it would answer a different question and could not be compared honestly with the committed full-inventory baseline.

## Error analysis
The failure is infrastructure/data-plane related, not evidence for or against reverse retrieval:
- Source 1 and truth access is healthy.
- Both target inventories are visible and downloadable according to Drive metadata.
- The failure occurs before analysis because the connector enforces a 268,435,456-byte per-file transfer ceiling.
- Splitting only the evaluation anchors would not solve the problem because reverse retrieval needs the complete target inventory to determine which S2/S3 records retrieve each S1 anchor.
- Sampling S2/S3 would distort posting frequencies, reverse ranks, recovered-positive counts, and the global cap competition.

## Risks / red-team checks
- No label-derived candidates or positive insertion occurred.
- No IDs were used as predictive evidence.
- No candidate-cap comparison was claimed without reproducing the baseline.
- No stale cache or local partial target inventory was substituted.
- No confirmation/frozen holdout was consumed.

## Recommendation
**BLOCKED.** Re-run R008 only in an environment with complete S2/S3 access, preferably the repository's private Modal volume after the runner hardening work is accepted, or with lossless target-source shards prepared specifically for ChatGPT Project execution. Preserve the exact 4,389-anchor calibration slice and cap-640 semantics.

## Follow-up
When full target access is available, implement reverse retrieval as a distinct provenance channel and first measure reverse-only recovered true pairs before changing matcher features or thresholds.
