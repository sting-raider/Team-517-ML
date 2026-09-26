# X010R — split-size-normalized anchor commonness audit

## Hypothesis

INT002 introduced country-local Source-1 name/address commonness features as
`ln(1 + frequency)`, and INT003 retained those v2 features. X009 showed that
raw counts are split-size-sensitive and that France has a small high-frequency
address tail outside the labeled fitting support.

The preregistered X010 hypothesis was that replacing raw count commonness with a
country-size-normalized representation would reduce same-country train→test
feature drift and reduce France out-of-fit-support exposure without using labels.

Two transforms were fixed before measurement:

1. **Per-million count:** `ln(1 + 1e6 * frequency / country_rows)`, empty = 0.
2. **Self-information:** `ln((country_rows + 1)/(frequency + 1))` for nonempty
   values, empty = 0.

## Change

Added a deterministic full-Source-1 audit helper:

`tools/experiments/x010_size_normalized_commonness.py`

It mirrors X009's normalization and exact INT002/INT003 fitting-anchor selection,
computes the current raw feature and both preregistered replacements on complete
train/test Source-1 populations, and reports:

- same-country train→test weighted KS distance,
- feature mean shift,
- actual 108,115-anchor fit support,
- France test support relative to the labeled fit range.

No production model, blocker, threshold, prediction, or candidate set is changed.

## Protocol

Complete supplied Source-1 populations were used, with **no sampling**:

| split | US | India | France | total |
|---|---:|---:|---:|---:|
| train | 1,323,633 | 883,188 | — | 2,206,821 |
| test | 663,106 | 809,986 | 259,452 | 1,732,544 |

Normalization follows the X009 semantic mirror of v2: lowercase, accent fold,
retain Unicode alphanumeric characters, punctuation to spaces, whitespace
normalization.

The actual selected-model fitting population was reconstructed with the repository
`sample517` MD5 ordering and `fold517` SHA-256 split:

- positions <= 30,000: fit fold only,
- positions 50,001–200,000: fit fold only,
- reconstructed fit anchors: **108,115**.

Reproduction command:

```bash
python tools/experiments/x010_size_normalized_commonness.py \
  --train /path/to/train_source1.tsv \
  --test /path/to/test_source1.tsv \
  --out reports/swarm/X010R-size-normalized-commonness.json
```

This ChatGPT runtime imposes a 60-second Python-call ceiling, so the complete
train and test scans were executed as two state-preserving calls rather than one
process. The train scan took **42.15 s** and the test scan **28.66 s**
(**70.81 s** core scan time). Neither file was sampled or truncated.

## Baseline / parity checks

The current raw representation reproduced the independent X009 measurements:

- fit anchor count: **108,115**,
- maximum fit name frequency: **253**,
- maximum fit address frequency: **14**,
- US name weighted KS: **0.066869**,
- US address weighted KS: **0.015850**,
- India name weighted KS: **0.034442**,
- India address weighted KS: **0.001495**.

Those checks make a normalization or fit-selection mismatch an unlikely
explanation for the result.

Current selected INT003 context remains unchanged: confirmation macro F0.5
**0.950198**, India **0.932699**, US **0.962081**, confirmation retrieval oracle
**0.980917**. Those values are context only. This audit does not evaluate or
retune the matcher.

## Results

### Same-country train→test drift

Weighted KS distance, lower is better:

| country / field | raw ln(1+freq) | per-million | self-information |
|---|---:|---:|---:|
| US name | **0.066869** | 0.641876 | 0.743643 |
| US address | **0.015850** | 0.943753 | 0.966868 |
| India name | **0.034442** | 0.556022 | 0.556022 |
| India address | **0.001495** | 0.951642 | 0.951642 |

Every preregistered normalized transform is dramatically farther apart across
same-country train/test populations than the current raw representation.

Mean feature shift (test minus train) points in the same direction:

| country / field | raw | per-million | self-information |
|---|---:|---:|---:|
| US name | -0.154390 | +0.272764 | -0.536810 |
| US address | -0.019128 | +0.345313 | -0.672072 |
| India name | -0.028459 | +0.030905 | -0.058062 |
| India address | -0.001711 | +0.046041 | -0.084810 |

The raw feature is not perfectly size-invariant, especially for US names, but
both proposed replacements make the measured distribution shift substantially
worse.

### France support relative to actual labeled fit

Fraction of France test anchors whose transformed feature lies outside the
minimum/maximum numeric range seen by the 108,115 fitting anchors:

| field | raw ln(1+freq) | per-million | self-information |
|---|---:|---:|---:|
| name | **0.0000%** | 1.9214% | 1.9969% |
| address | **0.3812%** | 4.1638% | 4.1638% |

The normalized variants therefore do not solve X009's France support concern.
They enlarge it. For address commonness, the out-of-fit-range rate rises by about
10.9x, from 0.3812% to 4.1638%.

Using the central fit 0.1%–99.9% interval gives the same qualitative conclusion:
France address exposure is 0.9181% under raw log-count, 5.2727% under
per-million normalization, and 11.1057% under self-information.

## Error analysis and mechanism

The failure is driven by a structural property of discrete inventory counts:
**frequency = 1 is a very large probability mass**, particularly for addresses.
Under raw `ln(1+frequency)`, a unique normalized value has the same feature
value in train and test. Under either proposed normalized representation, that
same unique string receives a different value solely because the country
inventory size changed.

Thus dividing a discrete count by country size does not make this feature
split-size invariant. It moves the dominant singleton-count mass whenever the
inventory size changes. A supplementary collision-only check (frequency > 1)
also showed larger KS under both normalized variants, so the failure is not
only a frequency-1 artifact.

No post-hoc transform was selected after seeing these results.

## Integrity / red-team checks

- Complete train/test Source-1 files were scanned; no feasibility sample was
  substituted.
- Fit-anchor reconstruction matches the selected model's exact 108,115 count.
- Raw X009 weighted-KS values and fit maxima reproduce independently.
- No labels, France pseudo-labels, S2/S3 approximation, candidate probabilities,
  confirmation window, leaderboard feedback, or external business data were used.
- Entity IDs are used only for deterministic sample/fold reconstruction, never
  as predictive features.
- The Python NFD normalizer is a semantic mirror rather than DuckDB's exact
  `strip_accents` implementation. Exact reproduction of X009's 253/14 fit
  maxima and all four quoted raw KS values materially reduces that parity risk.
- Weighted KS on discrete transformed supports can be sensitive to support
  movement. The mean-shift and France support measurements independently agree
  with the KS result.

## Risks

This is a **feature-design forensic**, not a matcher experiment. It does not
establish that the raw frequency feature is optimal, nor does it measure an
F0.5 change from replacing it. A production replacement would require rebuilding
the candidate features, retraining the matcher on the same candidate
distribution, calibration-only threshold selection, and held-out evaluation.

The complete S2/S3 files are still above this chat runtime's 256 MiB Drive
handoff ceiling, so the two target-side commonness features cannot be
recomputed end-to-end here.

## Recommendation

**REJECT** both preregistered size-normalized replacements.

Do not replace the current raw `ln(1+frequency)` commonness features with
per-million count or self-information in INT003. They materially worsen
same-country train→test drift and increase France out-of-fit-range exposure.

X009's original narrow France address-frequency tail still deserves attention.
A future matcher-capable experiment should test a deliberately bounded
alternative such as clipping/quantizing raw log-count or a collision-aware
bucket representation, with the transform fixed before scoring. That experiment
must retrain on the actual candidate pool and demonstrate no US/India macro
F0.5 or singleton-FPR regression before promotion.
