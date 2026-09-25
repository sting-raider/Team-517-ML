# R001 — Missed-positive taxonomy at cap 640

## Hypothesis
Classifying positive links missed by blocker v2 at cap 640 on the deterministic calibration partition would identify dominant country/source failure modes and guide complementary retrieval.

## Intended protocol
- Exact deterministic 30,000-anchor development sample used by the repository.
- Calibration fold only, matching `reports/retrieval_study.json`.
- Current blocker v2 at raw candidate cap 640.
- Full supplied training S1/S2/S3 inventory plus ground truth; no external identity data.

## Baseline verified from repository
- Calibration entities: 4,389.
- Candidate pair recall: 0.9458627913066248.
- Candidate entity recall: 0.9454912308973222.
- All-matches-retrieved rate: 0.8411892675852066.
- Blocking-oracle macro F0.5: 0.9811781091658961.
- Candidate-count p50/p90/p99/max: 597 / 640 / 640 / 640.
- Independent confirmation pair recall: 0.9472461073669532; oracle macro F0.5: 0.9809513534570724.
- Confirmation India pair recall: 0.9255885650224215 versus US 0.9625843588725684.

## Execution result
**BLOCKED before taxonomy computation.** Google Drive access itself was verified and `train_source1.tsv` (210,069,713 bytes) streamed successfully into the analysis runtime. The live connector rejected `train_source2.tsv` (489,301,488 bytes) and `train_source3.tsv` (503,705,637 bytes) because each exceeds its 268,435,456-byte per-file download limit. `train_ground_truth.tsv` is below the limit, but R001 requires the full S2/S3 inventory to reproduce candidate generation and inspect the text of every missed positive.

The documented lossless Project-file shard fallback was searched in the current Project/Library and was not present. GitHub intentionally contains neither raw challenge data nor row-level miss artifacts. No sample was substituted for the requested full-data analysis.

## Error analysis / partial evidence
The existing measurements already establish that misses are materially worse in India: confirmation pair-recall gap is about 3.70 percentage points (0.92559 India vs 0.96258 US), and India blocking-oracle macro F0.5 is 0.97139 vs 0.98759 US. This motivates R001 but is not a taxonomy.

## Risks
- Any taxonomy computed from only the downloadable prefix/files would be biased and violate the full-data protocol.
- Repeatedly inspecting the independent confirmation set would turn it into a tuning set; R001 should remain on development/calibration anchors.

## Recommendation
**BLOCKED / HANDOFF.** Re-run R001 in an environment with the existing full DuckDB/Modal volume, or attach the repository's lossless Drive shards so each materialized file is below the connector limit. Preserve the exact calibration slice and cap-640 baseline above.

## Follow-up
Once full S2/S3 bytes are available, classify every missed positive by name/address token overlap, character similarity, number agreement, missingness, target source, country, and whether the true target had zero keys versus keys that ranked below the cap. That distinction directly separates representation failures from ranking/capacity failures.