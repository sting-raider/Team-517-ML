# M006 — Wide retrieved hard-negative retraining

**Issue:** #78  
**Branch:** `agent/m/M006-wide-hard-negatives`  
**Baseline main:** `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`  
**Recommendation:** BLOCKED / FOLLOW-UP

## Hypothesis

The selected depth-10 CatBoost matcher is fit only on cap-80 candidate rows, while deployment/evaluation exposes much wider cap-160/640 candidate pools. Training on the actual wider retrieved-negative distribution may improve official per-anchor macro F0.5 and singleton precision, especially in India, without changing candidate recall.

## Change

No production matcher change was made because the required full S2/S3 data could not be materialized in this chat runtime. I verified the mismatch from current code and attempted two independent full-data execution paths before stopping.

## Protocol

Planned Tier-2 Variant A from Issue #78:

- exact established 30,000-anchor development population;
- fit/early folds regenerated at cap 160;
- same 47 features and depth-10 CatBoost configuration;
- same 4,389 calibration anchors and cap-160 candidate pool;
- compare official macro F0.5, singleton FP overall/India, US/India slices, candidate recall/oracle, threshold, rows/class balance, runtime;
- no confirmation/frozen holdout and no leaderboard feedback.

Execution-path checks:

1. **Connected Drive:** shared folder access was verified. The train folder exposes complete Source-1, Source-2, Source-3 and ground-truth TSVs.
2. **Connector raw transfer:** requesting complete `train_source2.tsv` with raw streaming failed with HTTP 413 because the 489,301,488-byte file exceeds the connector's 268,435,456-byte limit. Source-3 is also above the limit at 503,705,637 bytes.
3. **Disposable GitHub Actions runner:** a branch-only preflight workflow attempted to download Source-2 directly from the user-supplied Drive share. Run **36164847775** / job **108169985305** failed before runner allocation: the run completed in failure with no job steps. The temporary workflow was removed immediately after the preflight.

No sample was substituted for full S2/S3. No raw challenge data was committed or uploaded as an artifact.

## Baseline

The current selected depth-10 same-model calibration metrics remain:

- cap 80 macro F0.5: **0.924756**
- cap 160 macro F0.5: **0.927197**
- cap 640 macro F0.5: **0.930679**
- cap 160 pair recall: **0.925308**
- cap 160 blocking-oracle macro F0.5: **0.973081**
- cap 640 pair recall: **0.945863**
- cap 640 blocking-oracle macro F0.5: **0.981178**

M006a established that widening cap 80→640 adds about 1.614M calibration candidates for about 515 additional true links, so the marginal pool is roughly 0.0319% positive. This remains a strong motivation for M006, but it is not itself evidence that retraining helps.

## Result

**No empirical matcher result.** Variant A could not be run with complete target-source data in this environment. Therefore:

- new macro F0.5: **not measured**
- singleton FP delta: **not measured**
- India delta: **not measured**
- candidate recall/oracle change: **not applicable; no matcher variant was evaluated**

## Error analysis / blocker analysis

The blocker is environmental rather than scientific:

- Source-1 (210,069,713 bytes) and truth (127,015,583 bytes) are below the connector limit.
- Source-2 (489,301,488 bytes) and Source-3 (503,705,637 bytes) are not.
- The connector rejects the complete files before download, so local Python cannot legally reproduce the wide candidate pool.
- A remote GitHub Actions fallback also failed before any step executed, so it provided no alternate compute/data path.

Using only Source-1/truth would not test the stated hypothesis because the hard-negative distribution is defined by retrieved S2/S3 candidates. Replacing full targets with a sample would change both candidate ranks and negative composition and would not be a valid same-slice comparison.

## Risks checked

- **ID/label leakage:** no new features or candidates were created.
- **Split contamination:** no model run occurred; planned protocol retained fit/early versus calibration separation.
- **Candidate-cap mismatch:** no new metric accepted.
- **Stale caches:** no local candidate/model cache reused.
- **Sampling differences:** no sampled surrogate used.
- **Threshold leakage:** no threshold tuning performed.
- **Raw-data hygiene:** no raw challenge row committed; temporary workflow was removed.

## Recommendation

**BLOCKED / FOLLOW-UP.** M006 remains one of the stronger matcher hypotheses because the train/deployment negative-distribution mismatch is concrete. Recover it only in a runtime that can access complete S2/S3, preferably the existing Modal volume or lossless Project shards. The first decisive run should still be matched cap-160 training before attempting cap-640 hard-negative mining.

Do not claim a score gain from this branch.
