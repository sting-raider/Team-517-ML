# M004 — Opt-in address token soft-alignment features

**Issue:** #152  
**Branch:** `agent/m/M004-address-soft-alignment`  
**Baseline main:** `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`  
**Recommendation:** FOLLOW-UP / EMPIRICAL GATE REQUIRED

## Hypothesis

The current 47-feature CatBoost representation contains whole-string fuzzy address scores, exact token-set overlap, and number diagnostics, but it does not represent one-to-one fuzzy token alignment. A small language-agnostic address alignment block may expose evidence from token-local typos and reorderings without allowing repeated common tokens to be reused as multiple matches.

This is particularly plausible for India, where Source-1 addresses are materially longer in the supplied data, but no India score improvement is claimed here.

## Change

Added an opt-in five-feature block:

- `address_soft_left_coverage`
- `address_soft_right_coverage`
- `address_soft_hmean`
- `address_soft_strong_fraction`
- `address_soft_exact_fraction`

Implementation: `src/ber/soft_alignment.py`.

The matcher compares already-normalized address tokens. Exact token matches are consumed one-to-one first. Remaining token pairs receive Jaro-Winkler similarity only when both tokens have length >=3 and neither token is numeric. Numeric and short-token mismatches receive zero fuzzy credit. Remaining pairs are greedily assigned by descending similarity with token positions as deterministic tie breakers.

The existing `FEATURE_NAMES`, `features()`, and `batch_features()` paths are unchanged. The 52-feature schema is exposed only through `FEATURE_NAMES_SOFT_ALIGNMENT`, `features_with_soft_alignment()`, and `batch_features_soft_alignment()`.

## Protocol

### Synthetic semantics

Local Python tests exercised:

- empty addresses;
- reordered exact tokens;
- duplicate-token one-to-one constraints;
- numeric disagreement;
- local token typo credit;
- directional left/right coverage symmetry;
- bounded outputs;
- determinism;
- exact legacy 47-feature prefix parity.

Command:

```bash
PYTHONPATH=/tmp/m004 python -m unittest discover -s /tmp/m004/tests -v
```

Result: **9/9 passed**.

A separate deterministic randomized check compared the optimized exact-match fast path against the simpler full greedy cross-product on 5,000 synthetic token-list pairs. All five output values matched to 1e-12 in all **5,000 / 5,000** cases.

Local runtime versions were Python 3.13.5, RapidFuzz 3.14.3, NumPy 2.3.5. The repository pins RapidFuzz 3.14.5 and NumPy 2.3.2, so the normal repository environment must rerun tests before promotion.

### Complete Source-1 shape audit

The complete supplied `train_source1.tsv` was downloaded from the connected shared Drive and scanned locally: **2,206,821 rows, no sampling**.

For complexity only, raw whitespace-token counts were used rather than claiming production-normalization parity:

| Country | Rows | Mean address tokens | p50 | p90 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| US | 1,323,633 | 5.898 | 6 | 8 | 9 | 16 |
| India | 883,188 | 11.229 | 11 | 16 | 21 | 43 |

No row-level text or IDs were retained in the report.

### Runtime feasibility

Two runtime-only samples were taken from Source-1 file order. They are **not** score/effectiveness samples.

1. First 5,000 addresses per country, paired with the same tokens in reverse order:
   - before exact-token fast path: US 14.06 us/pair, India 62.84 us/pair;
   - after exact-token fast path: US 13.14 us/pair, India 11.13 us/pair.
2. First 3,000 addresses per country with a deterministic last-two-character swap applied to every eligible nonnumeric token and token order reversed:
   - US: 16.12 us/pair;
   - India: 57.42 us/pair.

A separate four-shape synthetic matcher microbenchmark over 10,000 pairs measured:
- legacy 47 features: **9.72 us/pair**;
- legacy + five alignment features: **20.38 us/pair**.

These timings are single-process local feasibility measurements, not production throughput claims.

## Results

### Correctness / representation result

The bounded implementation question succeeds:

- legacy feature vector remains exactly 47 values;
- the opt-in vector is 52 values;
- the first 47 values are exactly the legacy output in the parity test;
- duplicates cannot reuse the same target token;
- numeric mismatches are never fuzzily rewarded;
- empty/empty addresses receive zero soft-alignment credit rather than an artificial perfect match;
- exact token reordering yields full alignment credit;
- local typos can receive partial credit.

### Competition metric

**Not measured.**

No cap-160/640 S2/S3 candidate artifact is available in this chat runtime, and the connected Drive raw-transfer limit prevents materializing complete Source-2/Source-3. Therefore no official macro F0.5, singleton-FP, US/India delta, or feature importance is claimed.

Current selected confirmation context remains macro F0.5 **0.928835**, with India **0.900722**, but those numbers are baseline context only and were not re-evaluated in this task.

## Error analysis

The feature intentionally refuses several tempting forms of optimistic matching:

- **Repeated common tokens:** one target token can satisfy only one source token.
- **Address numbers:** `12` vs `13` receives no fuzzy token credit.
- **Short components:** non-exact tokens shorter than three characters receive no fuzzy credit.
- **Missing addresses:** two missing addresses are not treated as evidence of identity.
- **Weak token similarities:** scores below 0.60 never enter the assignment.

The remaining weakness is greedy assignment. It is deterministic and cheap but not guaranteed to maximize total alignment score globally. A Hungarian/optimal assignment would be a different experiment and is not justified until this cheaper block shows empirical value.

## Interpretation

The feature fills a real representation gap without touching candidate generation or the selected 47-feature path. The full Source-1 audit also shows why runtime must be treated seriously: India addresses contain roughly twice as many whitespace tokens as US addresses, so a naive token cross-product disproportionately taxes the already-weaker India slice.

Pre-consuming exact matches removes most of that cost when addresses share many intact tokens, but heavily corrupted long addresses remain expensive. This makes the block suitable for an empirical matcher ablation, not automatic production promotion.

## Risks

- **No F0.5 evidence yet.** A plausible feature is still just a plausible feature.
- **Calibration reuse:** the designated development calibration fold has already seen substantial model selection. Any tiny gain must be treated skeptically and paired-diff/bootstrap checked.
- **Runtime:** worst-case fuzzy cross-products scale with unmatched token counts; India is the higher-risk slice.
- **Version drift:** local RapidFuzz/NumPy versions differ slightly from repo pins.
- **Normalization audit:** the full Source-1 complexity table uses raw whitespace-token counts only; it is not presented as exact post-normalization token statistics.
- **Native fast features:** the opt-in Python path has no C++ extension implementation. Default/native legacy behavior is untouched.
- **France:** the block is language-agnostic, but no French accuracy is inferable because France has no labels.

## Recommendation

**FOLLOW-UP / EMPIRICAL GATE REQUIRED.**

The implementation is safe as an opt-in experiment primitive and preserves legacy behavior. Promotion requires a same-candidate matcher ablation in a runtime with complete target-source artifacts:

1. identical fold517 fit/early/calibration anchors;
2. identical candidate IDs and cap;
3. depth-10 baseline 47 features versus 52 features;
4. threshold recalibration only on the designated calibration fold;
5. report official macro F0.5, singleton FP overall/India, US/India, candidate recall/oracle parity, runtime, and paired anchor-level changes;
6. treat sub-0.001 gains as fragile and replicate before any fresh integration holdout.

## Follow-up

The highest-value follow-up is the direct 47-vs-52 same-candidate ablation on the existing private/Modal feature artifacts. Do not spend a confirmation window before that development evidence exists.
