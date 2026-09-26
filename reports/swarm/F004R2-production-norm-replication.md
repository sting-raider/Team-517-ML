# F004R2 — Production-normalization replication of same-address hard negatives

**Issue:** #137  
**Recovery branch:** `agent/i/F004R2-production-norm-replication`  
**Recommendation:** **PROMOTE** the F004 forensic counts as production-normalization-exact for the supplied train Source-1 corpus. This does **not** promote a model change; hard-negative integration still needs matched-pool evaluation.

## Hypothesis

F004's same-address hard-negative signal is qualitatively useful, but F004R correctly identified one unresolved provenance gap: F004 grouped addresses with a Python NFD/Mn fallback instead of the exact latest-main DuckDB `strip_accents` path. If the 554 non-ASCII address rows normalize differently, collision membership and pair mass could shift.

## Exact change

Added a bounded, Source-1-only replication helper that:

1. reproduces F004's two-pass full-corpus collision census;
2. audits every non-ASCII address row against the semantics used by the repository-pinned DuckDB 1.5.5 implementation;
3. recomputes collision counts and the F004 name-confusability diagnostics; and
4. emits only aggregate JSON.

No retrieval, matcher, threshold, candidate-cap, or submission behavior changed.

The repository pins `duckdb==1.5.5`. Its `strip_accents` implementation calls vendored `utf8proc_remove_accents`; the pinned vendored implementation maps with `UTF8PROC_STABLE | UTF8PROC_COMPOSE | UTF8PROC_STRIPMARK`. Latest-main `src/ber/data.py` then lowercases and collapses non-Unicode-letter/number runs. The helper emulates those semantics only to prove parity on the **observed corpus codepoint domain**; it is explicitly not a general replacement for DuckDB on arbitrary Unicode.

## Protocol

- Base: `main` @ `f08c041b274e58ae900620ac714ec8a0a06f09b0`.
- Data: complete supplied `train_source1.tsv`; **2,206,821 rows**, **210,069,713 bytes**, SHA-256 `591af0e1dfeb65cab71ea6ee8cb69df00f92d6ba6fa79e05746c938775d14973`.
- Countries: US 1,323,633; India 883,188.
- No sampling.
- No ground truth.
- No S2/S3.
- No confirmation or frozen holdout.
- No external business/identity data.
- Entity IDs are not used as evidence or grouping keys.
- Full command:
  `python tools/experiments/f004r2_production_norm_replication.py --input /mnt/data/train_source1.tsv --output reports/swarm/F004R2-production-norm-replication.json`
- Focused test:
  `python tests/test_f004r2_production_norm_replication.py`
- Full execution: **23.39 s wall**, **695.36 MiB peak RSS**.
- Focused tests: **2/2 PASS**.

## Baseline

F004 / PR #29 reported, under its Python fallback:

| Metric | All | India | US |
|---|---:|---:|---:|
| Collision groups | 40,511 | 15,367 | 25,144 |
| Collision rows | 117,160 | 42,709 | 74,451 |
| Collision-row rate | 5.3090% | 4.8358% | 5.6247% |
| Cross-name pairs | 153,505 | 50,164 | 103,341 |
| Shared-name-token pair rate | 20.90% | 38.75% | 12.23% |
| Name Jaccard > 0.25 | 8.28% | 24.88% | 0.22% |

F004R / PR #142 left these exact counts as FOLLOW-UP because 530 of the 554 non-ASCII rows sat outside the Python-defined collision groups and could, in principle, have merged under DuckDB normalization.

## Results

### Normalization parity

The complete corpus contains **554 non-ASCII address rows** and **0 non-ASCII business-name rows**. Across every one of those 554 rows:

- F004 fallback vs production-semantic normalization mismatches: **0**
- non-ASCII collision rows: **24**, all in India
- previously concerning non-collision non-ASCII rows: **530**
- rows whose collision membership can change because of the normalization difference: **0**

The observed non-ASCII address domain contains 13 codepoints. It is dominated by mojibake-like C1 bytes plus `Â/â`, `Ï/ï`, `½`, `¿`, and `¬`. In this domain, F004's lower→NFD→remove-Mn path and DuckDB's strip-mark→compose→lower path collapse to identical final Unicode-letter/number tokens.

This closes the specific F004R gap. It is a corpus-domain parity result, not a claim that the two normalizers are universally equivalent.

### Full collision census

The independent full-data recomputation reproduces F004 **exactly**:

| Metric | F004 | F004R2 | Delta |
|---|---:|---:|---:|
| Collision groups | 40,511 | **40,511** | **0** |
| Collision rows | 117,160 | **117,160** | **0** |
| Collision-row rate | 5.308994% | **5.308994%** | **0 pp** |
| Collision pairs | 153,505 | **153,505** | **0** |
| Same-name pairs | 0 | **0** | **0** |
| Cross-name pairs | 153,505 | **153,505** | **0** |

Country counts also reproduce exactly:

- **India:** 15,367 groups; 42,709 rows; 50,164 cross-name pairs; 4.835777% collision-row rate.
- **US:** 25,144 groups; 74,451 rows; 103,341 cross-name pairs; 5.624746% collision-row rate.

### Confusability and concentration

The original hard-negative interpretation also reproduces exactly:

| Diagnostic | All | India | US |
|---|---:|---:|---:|
| Cross-name pairs sharing ≥1 name token | 20.8977% | **38.7469%** | 12.2333% |
| Name-token Jaccard > 0.25 | 8.2792% | **24.8804%** | 0.2206% |
| Compact first-6 prefix equal | 0.3036% | **0.6319%** | 0.1442% |
| 6+ groups as share of groups | 7.2449% | 4.8415% | 8.7138% |
| Pair mass from 6+ groups | 39.2906% | 28.4626% | 44.5467% |

Group-size quantiles remain p50/p90/p99/max = 2/5/8/14 overall, 2/5/7/13 for India, and 2/5/8/14 for US.

## Error analysis / red-team checks

- **Normalization drift:** resolved on all 554 potentially sensitive address rows; zero mismatches.
- **Split contamination:** none; no labels or evaluation folds are read.
- **ID leakage:** entity IDs are not used as evidence or grouping keys.
- **Sampling differences:** none; complete Source-1 file was scanned twice.
- **Candidate-cap / threshold mismatch:** N/A; this is a Source-1 forensic audit.
- **Stale cache:** none; the helper streams the raw TSV and builds in-memory counters from scratch.
- **Metric bug:** collision pair arithmetic is independently recomputed as n(n-1)/2, with same-name mass subtracted from total pair mass; focused synthetic tests cover cross-name grouping and accent parity.
- **External identity leakage:** none. Public DuckDB source was consulted only to pin normalization implementation semantics.

The first attempt to run the extracted helper narrowly exceeded the notebook subprocess watchdog before the ASCII fast path was added. After the optimization, the **same full-data helper completed successfully in 23.39 s** and produced the committed aggregate JSON. This is a runtime/tooling detail, not a scientific exclusion.

## Risks

- This validates F004 on the supplied **train Source-1** corpus only. It does not establish S2/S3 collision rates or an end-to-end F0.5 gain.
- The parity proof is restricted to the 13 non-ASCII codepoints actually observed here. Future/unseen Unicode can still differ between the lightweight Python audit emulation and DuckDB.
- Source-1 same-address competition is still a proxy for matcher hard negatives. The actual value of mining/weighting these examples must be measured on the current INT003 candidate pool.

## Recommendation

**PROMOTE** the F004 forensic result and remove the “exact production-normalized counts unverified” caveat for this corpus. The zero-delta replication means the 40,511 / 117,160 / 153,505 counts and India confusability diagnostics are safe to use as evidence for experiment design.

The highest-value modeling follow-up remains a controlled current-v3 hard-negative experiment: mine production-normalized same-address competing anchors, emphasize the Indian partial-name-overlap slice, retrain on the exact same candidate population, and evaluate official macro F0.5 plus singleton FP on the same fixed evaluation examples. No hard “same address means non-match” rule is justified.