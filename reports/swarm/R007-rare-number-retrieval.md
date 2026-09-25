# R007 — rare-number high-precision retrieval blocks

## Hypothesis
Dedicated source-specific rare numeric-token blocks, especially address-number keys, may recover true S1→S2/S3 links missed by blocker v2 with much less candidate growth than generic token expansion.

## Change
No retrieval change was committed because the required full target inventories could not be transferred into this ChatGPT runtime. I inspected the current blocker (`src/ber/blocking.py`) and verified that blocker v2 already uses first/last address-number composite keys (`h:`/`z:`) but does not expose a dedicated exact numeric-token channel suitable for the planned DF ablation.

## Protocol
- Branch: `agent/r/R007-rare-number-retrieval`
- Intended evaluation: established deterministic development/calibration anchors, blocker-v2 cap 640, identical anchors and cap semantics.
- Data source: supplied Google Drive challenge folder only.
- Drive files verified:
  - train_source1.tsv: 210,069,713 bytes — successfully streamed to the analysis container.
  - train_ground_truth.tsv: 127,015,583 bytes — successfully streamed to the analysis container.
  - train_source2.tsv: 489,301,488 bytes — connector rejected the raw transfer at 268,435,456 bytes.
  - train_source3.tsv: 503,705,637 bytes — exceeds the same connector ceiling.
- Direct network download from the analysis container is unavailable (DNS/network disabled).
- No sample or partial S2/S3 surrogate was substituted.

## Baseline
Current recorded confirmation context only, **not re-evaluated here**:
- candidate pair recall at cap 640: 0.947246
- blocking-oracle macro F0.5: 0.980951
- official macro F0.5: 0.928835

## Results
**BLOCKED — no empirical retrieval metric claimed.**

The full S2/S3 target inventories are required to build source-specific numeric document frequencies, generate candidate unions, and measure recovered positive links. Source-1-only analysis would overlap active F003a and cannot answer R007's retrieval question.

## Error analysis
The blocker is environmental rather than scientific:
1. Source 1 and truth are small enough for the connector and work in local Python.
2. Source 2 and Source 3 each exceed the connector's 256 MiB raw-download limit.
3. The container cannot independently fetch Drive URLs.
4. Existing repo reports do not contain row-level candidate inventories sufficient to reconstruct an R007 comparison.

## Risks / red-team checks
- No labels inserted into candidate pools.
- No record IDs used as predictors.
- No confirmation/frozen holdout consumed.
- No cap change or threshold retuning occurred.
- No stale cache was used because no retrieval run was performed.
- No external business data was used.

## Recommendation
**BLOCKED / FOLLOW-UP.** Execute R007 in the shared Modal data plane or after lossless S2/S3 shards below the connector ceiling are available. Do not infer a gain from Source-1 rare-number prevalence alone.

## Follow-up
The exact required handoff is a runtime with complete train_source2.tsv and train_source3.tsv, or lossless shards of those files. Then evaluate DF cutoffs on the established calibration anchors against blocker v2 at identical cap 640.