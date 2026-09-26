# X009 — INT002 anchor-frequency feature transfer audit

## Hypothesis

INT002 added four inventory-frequency features and two retrieval-rank features to the original 47-feature matcher. Two additions are anchor-side and available from Source-1 alone: log_anchor_name_frequency and log_anchor_address_frequency.

The v2 pipeline computes country-local normalized-string counts and feeds ln(1 + frequency) to CatBoost. Inference rebuilds those counts on the test inventory. The question is whether these two inputs move outside the numeric support actually seen by INT002 fitting anchors, especially for unlabeled France.

## Exact change

Added tools/experiments/x009_int002_frequency_shift.py plus focused tests. The helper scans complete train/test Source-1 files, mirrors the repository normalization semantics with Unicode NFD accent removal + lowercase + Unicode alphanumeric retention, counts normalized name/address values by country, reconstructs the exact INT002 sample/fold selection, and compares train/test feature-frequency distributions.

No production scoring path changes.

## Protocol

Complete supplied Source-1 population, no sampling:
- train Source-1: 2,206,821 rows
- test Source-1: 1,732,544 rows
- test France: 259,452
- test US: 663,106
- test India: 809,986

INT002 fitting reconstruction:
- sample517 MD5 ordering
- positions <=30,000 plus positions 50,001–200,000 according to current v2 selection
- fold517 SHA256 split from src/ber/experiment.py
- reproduced fitting-anchor count: 108,115 exactly
- fit anchors: India 43,160 / US 64,955

Reproduction command:

    python tools/experiments/x009_int002_frequency_shift.py \
      --train train_source1.tsv \
      --test test_source1.tsv \
      --out reports/swarm/X009-int002-frequency-shift.json

Measured scan time: train 50.40 s + test 33.61 s = 84.01 s. Peak RSS was not instrumented with time -v; polling observed roughly 949 MiB near the end of the test scan.

Integrity checks:
- complete train/test row counts reproduce repository census
- INT002 fit count reproduces 108,115
- fit-observed maximum normalized name frequency = 253
- fit-observed maximum normalized address frequency = 14
- these 253/14 bounds match prior full-Source-1 commonness context cited by R023/D001a
- 7 focused helper assertions + 5 empirical integrity assertions passed

DuckDB is absent in this runtime, so the normalizer is a semantic Python NFD mirror rather than byte-for-byte strip_accents. Reproducing the established frequency maxima reduces, but does not eliminate, parity risk.

## Baseline context

Selected INT002 confirmation is unchanged:
- macro F0.5: 0.940478
- India: 0.913639
- US: 0.958045
- singleton FP rate: 5.818%
- candidate cap: 160
- threshold: 0.65

France has no labels. No France score is claimed.

## Results

### Actual fitting support

Across the 108,115 INT002 fitting anchors:

| feature | p50 | p90 | p99 | p99.9 | max |
|---|---:|---:|---:|---:|---:|
| anchor name frequency | 1 | 34 | 93 | 204 | 253 |
| anchor address frequency | 1 | 1 | 5 | 9 | 14 |

The fitted model therefore saw log_anchor_address_frequency only up to ln(15) = 2.7081.

### France name frequency remains inside the fit maximum

France test name frequency:
- collision-row rate: 34.406%
- p90 / p99 / p99.9 / max: 11 / 71 / 157 / 205
- mean log1p(freq): 1.158549 vs fit 1.365346
- rows above fit max 253: 0
- rows above fit p99.9 frequency 204: 205 / 259,452 = 0.0790%

There is no high-side name-frequency extrapolation beyond the fitting maximum.

### France address frequency has a real out-of-support tail

France test address frequency:
- collision-row rate: 11.106%
- p90 / p99 / p99.9 / max: 2 / 9 / 86 / 101
- mean log1p(freq): 0.785868 vs fit 0.733748
- 989 anchors (0.3812%) exceed the fit maximum frequency 14
- 2,382 anchors (0.9181%) exceed the fit p99.9 frequency 9
- France maximum model value ln(102) = 4.6250 vs fit max ln(15) = 2.7081

Zero US/India test anchors exceed fit max 14 for address frequency. France's address collision-row rate is 2.75x US test and 2.35x India test.

This is a narrow tail, not a population-wide failure, but it is genuine model-input extrapolation concentrated in the unlabeled country.

### Raw count frequency is split-size-sensitive

Same-country train→test drift:

| country / field | weighted KS | mean log1p delta | collision-rate delta |
|---|---:|---:|---:|
| US name | 0.0669 | -0.1544 | -6.687 pp |
| US address | 0.0158 | -0.0191 | -1.585 pp |
| India name | 0.0344 | -0.0285 | -0.642 pp |
| India address | 0.0015 | -0.0017 | -0.108 pp |

US test Source-1 inventory is 50.10% of US train size; India test is 91.71% of India train size. The much larger US name-frequency shift is consistent with raw counts carrying split-size information. This is not proof of score harm, but it motivates a relative-frequency / IDF-style representation.

## Error analysis / red-team

- No labels are used in this distribution audit.
- No France pseudo-labels or leaderboard feedback.
- No S2/S3 sample or proxy substituted.
- Entity IDs are used only for deterministic sample/fold reconstruction, never as predictive features.
- No confirmation/frozen evaluation consumed.
- Fit selection reproduces the selected model's 108,115 anchors.
- Python NFD normalization is approximate vs DuckDB strip_accents, but the established 253/14 maxima reproduce exactly.
- Only two of INT002's four inventory-frequency features are audited. Target name/address frequency needs complete S2/S3, unavailable here because each exceeds the Drive connector's 256 MiB raw handoff.
- Out-of-support does not imply wrong predictions. CatBoost trees do not extrapolate like a linear model; direction and France score impact remain unknown.
- Raw frequency is recomputed independently on train/test inventories, so population size is a built-in confounder.

## Recommendation

FOLLOW-UP.

Do not alter the submitted INT002 model from this audit alone. On a runtime with the private candidate/feature volume, preregister one robust frequency variant: clip log1p(freq) to fit-support bounds or replace raw count with country/source-size-normalized commonness or IDF. Retrain on the same INT002 candidate distribution and fitting anchors, tune only on the existing calibration protocol, inspect the existing holdout, and do not reuse the consumed 40,001–45,000 confirmation window for tuning.

Require no meaningful US/India macro F0.5 or singleton-FPR regression. France should be inspected only for feature-domain coverage, never with invented labels.

The X009 finding is therefore a concrete France robustness risk and a design hint for the next matcher iteration, not a France accuracy claim.
