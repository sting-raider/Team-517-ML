# R024 — matcher-coupled complementary character retrieval at cap160

## Recommendation

**BLOCKED / HANDOFF.** The scientific question remains high-value, but this runtime cannot execute the matched-pool retraining without complete Source-2/3 or access to the private Modal candidate/feature volume.

No matcher score, macro F0.5 delta, or candidate recall delta is claimed.

## Hypothesis

The already measured complementary character retrieval pools at cap160 may improve official macro F0.5 after retraining the selected INT002-style 53-feature matcher on the changed candidate distribution.

The two required candidate pools from reports/int001_retrieval.json are:
- base + character RRF160: oracle 0.9808095251, pair recall 0.9456664048, mean candidates 148.05
- source-aware + character RRF160: oracle 0.9810863960, pair recall 0.9470411102, mean candidates 155.50

The source-aware variant is slightly stronger overall but weaker on India pair recall than base+char, so a matcher-coupled paired comparison is required before promotion.

## Intended protocol

- exact 4,389 calibration anchors for paired candidate-pool comparison
- no tuning on the consumed 40,001–45,000 matcher-confirmation window
- INT002-compatible 53-feature design with score-only dense rank
- same cap160 and same evaluation examples
- retrain separately on each changed candidate distribution
- report official entity macro F0.5, singleton FPR, pair/entity/all-matches retrieval recall, blocker oracle, US/India slices, candidate counts, runtime/memory
- red-team stale caches, candidate-cap equality, ID/label leakage, split contamination, and threshold scope

## Execution evidence

Shared Drive access was verified.

Files that successfully mount through the live Drive raw handoff:
- train_source1.tsv: 210,069,713 bytes
- train_ground_truth.tsv: 127,015,583 bytes

Required target inventories exceed the connector handoff limit:
- train_source2.tsv: 489,301,488 bytes
- train_source3.tsv: 503,705,637 bytes
- raw handoff limit observed: 268,435,456 bytes

The connector rejects Source-2 before returning a raw file handle. No partial/truncated target corpus was substituted.

A prior swarm fallback was also checked rather than blindly repeated:
- R004 GitHub Actions run: 36165064353
- job: 108170686585
- conclusion: failure
- runner_id: 0
- executable steps: zero

So the Actions path failed before a runner was allocated; it is not a usable full-data escape hatch in this repository/runtime as currently configured.

Local runtime capability check:
- CatBoost 1.2.8 available
- RapidFuzz available
- no DuckDB package
- no Modal Python package or modal CLI
- container outbound git/DNS unavailable

The private Modal volume referenced by SUBMISSION_2.md contains the complete candidate artifacts, but this chat has no authorized Modal tool/path.

## Baseline context

Current selected model:
- INT002 cap160 depth10, 53 features, threshold 0.65
- confirmation macro F0.5 0.940478
- India 0.913639
- US 0.958045
- singleton FPR 5.818%
- confirmation retrieval oracle 0.974176

Retrieval-only evidence on the established 4,389 calibration anchors:
- legacy base160 oracle 0.9730807315, pair recall 0.9253076722
- base+char RRF160 oracle 0.9808095251, pair recall 0.9456664048
- source-aware+char RRF160 oracle 0.9810863960, pair recall 0.9470411102
- source-aware+char India pair recall 0.9172402491 vs base+char 0.9188790560

These are oracle/retrieval measurements only, not matcher outcomes.

## Error analysis / integrity

- No target sample was substituted.
- No external entity/business data used.
- No labels inserted into retrieval.
- No record-ID feature introduced.
- No confirmation/frozen matcher window consumed.
- No stale candidate cache reused.
- Existing int001_retrieval.json is treated only as prior measured retrieval evidence.
- The failure is a data-plane/compute-access limitation, not a negative model result.

## Handoff

Recover R024 only in a runtime that can read complete S2/S3 or the private Modal volume. Reuse the exact INT001 retrieval definitions and INT002 matcher protocol. Train/evaluate both base+char RRF160 and source-aware+char RRF160 on the same anchors, because the latter's small overall retrieval advantage trades off against slightly weaker India recall.

Do not infer a matcher gain from the oracle gain alone.
