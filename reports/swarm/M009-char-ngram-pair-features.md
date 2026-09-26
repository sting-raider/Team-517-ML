# M009 — Opt-in pairwise character n-gram similarity features

## Recommendation

**FOLLOW-UP / EMPIRICAL GATE.**

The selected INT003 matcher has no explicit pairwise character n-gram overlap feature. This branch adds an opt-in eight-feature primitive while leaving the existing 47-feature base schema and therefore the selected 57-feature V3 schema unchanged by default.

This session could not execute the repository Python tests because every Python/container backend began failing with a platform-level `ClientError` before user code started. The feature equations were independently exercised in the available V8 execution surface, but this is not a substitute for the Python test suite or an end-to-end CatBoost ablation. No macro-F0.5 gain is claimed.

## Hypothesis

Explicit compact character 3/4-gram overlap can expose substring and spacing-tolerant evidence that is not represented directly by the current edit/Jaro/token feature family. Because the representation is language-agnostic, it is also a plausible low-risk primitive for India and unseen-France robustness.

## Current baseline and source audit

Latest-main `src/ber/features.py` has 47 base features:
- fuzzy ratio / token-sort / token-set / compact ratio;
- Jaro-Winkler and exact equality;
- length and token overlap;
- numeric overlap/agreement/conflict;
- missingness;
- retrieval score, key hits, target source.

V2 appends six inventory-frequency/rank features (53 total). INT003 V3 appends four lexical/character retrieval-provenance features (57 total).

No existing matcher feature computes explicit character n-gram set overlap. The currently selected INT003 confirmation score is **0.9501984899746141** at cap160/threshold0.625; that number is context only, not a baseline-vs-M009 paired comparison in this task.

## Exact change

`src/ber/features.py` now defines a separate opt-in block:
- name char-3 Jaccard
- name char-3 containment
- name char-4 Jaccard
- name char-4 containment
- address char-3 Jaccard
- address char-3 containment
- address char-4 Jaccard
- address char-4 containment

Character grams are built from the normalized string after removing spaces. This deliberately makes the block invariant to spacing changes already erased by compaction. Jaccard measures symmetric overlap; containment is intersection divided by the smaller gram-set size and therefore distinguishes a clean substring from an exact match.

Missing text and strings shorter than the requested n emit zero evidence rather than treating two missing/too-short fields as a match.

The existing `FEATURE_NAMES`, `features()`, and `batch_features()` behavior is untouched. Callers must explicitly request `batch_char_ngram_features()` and append the eight names themselves. This avoids silently changing any saved model schema or production inference path.

## Protocol

Tier 0:
1. Inspect latest-main `features.py`, `v2.py`, `v3.py`, and `predict.py`.
2. Verify no explicit char n-gram pair feature exists.
3. Add only the opt-in primitive and focused tests.

Tier 1 reference checks:
- deterministic exact-match case;
- spacing-only case;
- substring case;
- unrelated strings;
- missing strings;
- deterministic 100,000-pair synthetic reference microbenchmark.

No challenge target text, candidate labels, confirmation/frozen holdout, France labels, leaderboard feedback, external data, or record IDs as predictors were used.

## Executed reference results

Independent V8 reference implementation of the same equations produced:

| Case | 3-gram Jaccard | 3-gram containment | 4-gram Jaccard | 4-gram containment |
|---|---:|---:|---:|---:|
| exact | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| spacing-only (`acme pvt ltd` vs `acmepvtltd`) | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| substring (`acme technologies private limited` vs `acme technologies`) | 0.5000 | 1.0000 | 0.4815 | 1.0000 |
| unrelated | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| missing | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Reference microbenchmark: **100,000 synthetic pairs in 4.381 s (~22,826 pairs/s)** in the V8 execution surface. This is only a feature-math sanity/runtime signal; it is **not** the Python/RapidFuzz production throughput and must not be used for capacity planning.

## Python test status

Added `tests/test_char_ngram_features.py` with five focused tests covering:
- exact preservation of the legacy 47-feature schema;
- exact/spacing-equivalent n-gram behavior;
- substring containment vs Jaccard;
- neutral missing/too-short behavior;
- batch shape, dtype, range, and determinism.

**Not executed in this session.** Both private Python and container execution returned a platform `ClientError` before user code ran; a separate user-visible Python executor failed identically. Claiming these tests passed would therefore be fabricated.

## Error analysis / risks

1. **Redundancy risk.** Compact edit ratio and Jaro-Winkler already encode related character evidence. Only a same-candidate CatBoost ablation can establish incremental value.
2. **CPU/memory risk.** Set construction is more expensive than scalar fuzzy features. The 50k-entry gram cache bounds reuse but production Python throughput remains unmeasured.
3. **Normalization inheritance.** The feature consumes the current normalized strings, so accent-folding behavior remains whatever the active data normalizer produces. X002 already showed France-specific collision inflation from folding; a later Unicode-preserving parallel view is a separate experiment.
4. **Short-string behavior.** Strings shorter than n intentionally yield zero for that n. Existing exact/fuzzy features retain responsibility for those cases.
5. **No score claim.** The current session has neither complete S2/S3 transfer nor private INT003 candidate/model artifacts, so there is no valid same-slice macro-F0.5 comparison.

## Required empirical gate

On the private full-data lane:
1. append these eight features to the current V3 57-feature matrix only;
2. keep the exact same fused cap160 candidates and 108,115 fit-anchor protocol;
3. train the same depth-10 CatBoost;
4. calibrate threshold only on the designated calibration fold;
5. compare against INT003 on identical anchors/candidates;
6. report official macro F0.5, US/India, singleton FPR, threshold, candidate recall/oracle parity, runtime, and paired anchor bootstrap/diff.

Treat a sub-0.001 gain skeptically unless the paired error set and uncertainty support it.

## Artifacts

- Branch: `agent/m/M009-char-ngram-pair-features`
- Issue: #253
- Implementation commit: `da57f6a74a1b83ade196311ada5d2f81fc4d7a68`
- Test commit: `8db3e7f020b16d8757236b0f015981c2c0f6e4c8`
- `src/ber/features.py`
- `tests/test_char_ngram_features.py`

Raw challenge records, predictions, model binaries, and row-level diagnostics are not committed.
