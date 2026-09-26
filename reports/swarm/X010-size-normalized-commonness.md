# X010 — split-size-invariant anchor commonness audit

## Hypothesis

INT002 introduced country-local anchor name/address frequency features as `ln(1 + count)`, and INT003 inherits those features. X009 showed that raw counts shift with inventory size and that France has an address-frequency tail outside the labeled fit support. X010 preregistered two apparently size-normalized replacements:

1. per-million count: `ln(1 + 1e6 * freq / country_rows)`, with empty text fixed at 0;
2. self-information: `ln((country_rows + 1) / (freq + 1))` for nonempty text, with empty text fixed at 0.

The hypothesis was that one of these representations would reduce US/India train→test numeric drift while bringing France back inside the support seen by labeled fitting anchors.

## Change

Added `tools/experiments/x010_size_normalized_commonness.py` and focused tests. This is analysis-only. No production feature, matcher, retrieval, threshold, submission, or prediction behavior changes.

## Protocol

Complete supplied Source-1 inventories, no sampling:

- train Source-1: **2,206,821** rows
- test Source-1: **1,732,544** rows
- train US / India: **1,323,633 / 883,188**
- test US / India / France: **663,106 / 809,986 / 259,452**

Normalization mirrors X009 and v2 semantics: lowercase, Unicode NFD accent removal, Unicode alphanumeric retention, punctuation-to-space, whitespace collapse. The helper reconstructs sample517 MD5 ordering and fold517 SHA256 assignment, then selects the same fit population used by INT002/INT003: positions <=30,000 plus fit-fold positions 50,001–200,000. The exact fitting-anchor count reproduced: **108,115** (India 43,160, US 64,955).

Full-population scan runtime in this ChatGPT environment: **73.75s** (43.19s train + 30.57s test). The local command runner has a shorter wall-clock ceiling, so the exact train/test scans were executed as deterministic bounded stages and aggregate counters were then combined. No row was omitted.

Reproduction:

```bash
python tools/experiments/x010_size_normalized_commonness.py \
  --train train_source1.tsv \
  --test test_source1.tsv \
  --out reports/swarm/X010-size-normalized-commonness.json

python -m unittest tests/test_x010_size_normalized_commonness.py -v
```

Focused validation: **7/7 tests PASS**. Empirical integrity checks reproduce X009's fit maxima exactly: raw name frequency **253**, raw address frequency **14**, and fit-anchor count **108,115**.

Current score context is INT003, not a metric result from this task: confirmation macro F0.5 **0.950198**, India **0.932699**, US **0.962081**, candidate oracle **0.980917**, cap160, threshold0.625. X010 consumes no labels, calibration probabilities, confirmation window, or leaderboard feedback.

## Results

### Same-country train→test numeric drift

Weighted KS on exact numeric feature values:

| Country / field | raw `ln(1+freq)` | per-million | self-information |
|---|---:|---:|---:|
| US name | 0.066869 | 0.641876 | 0.743643 |
| US address | 0.015850 | 0.943753 | 0.966868 |
| India name | 0.034442 | 0.556022 | 0.556022 |
| India address | 0.001495 | 0.951642 | 0.951642 |

Both proposed transforms are dramatically worse on all four same-country comparisons. This is not a tiny-sample wobble: the relative transforms move the numeric value attached to a singleton whenever `country_rows` changes. For US, a singleton maps from **0.562752** in train to **0.919507** in test under the per-million transform, while raw remains `ln(2)=0.693147` in both. Under self-information, the same US singleton shifts from **13.402744** to **12.711544**.

Mean numeric deltas tell the same story. US address changes only **-0.019128** under raw, versus **+0.345313** per-million and **-0.672072** self-information. India address raw delta is **-0.001711**, versus **+0.046041** and **-0.084810**.

### France support relative to labeled fit

Rows outside the numeric min/max observed over the exact 108,115 fitting anchors:

| France field | raw | per-million | self-information |
|---|---:|---:|---:|
| name | 0 (0.0000%) | 4,985 (1.9214%) | 5,181 (1.9969%) |
| address | 989 (0.3812%) | 10,803 (4.1638%) | 10,803 (4.1638%) |

The preregistered normalization does the opposite of the hoped-for France robustness fix:

- France name goes from **0%** outside fit range under raw frequency to roughly **1.9–2.0%** outside under the relative transforms.
- France address goes from **989 rows / 0.3812%** outside fit range to **10,803 rows / 4.1638%** under either relative transform.

For France address, the per-million maximum is **5.966870** versus a labeled-fit maximum **2.754896**. Self-information reverses direction but not the support problem: the France minimum is **7.841358** versus labeled-fit minimum **11.052237**.

## Error analysis

The failure mechanism is structural, not a threshold accident. Country-size normalization based on the observed split size does not make low-count empirical frequencies split-invariant. For singleton-heavy business names and especially addresses, `freq=1` is stable under raw counts but the proposed formulas explicitly inject `country_rows`. When train and test inventory sizes differ, the most common feature value moves en masse. Weighted KS correctly sees this as numeric model-input drift; CatBoost thresholds also see a different numeric value.

The France address collision tail is therefore not explained away by country inventory size. Relative scaling makes it more extreme because a repeated address in the smaller French inventory represents a larger observed share.

## Risks / red-team

- No labels, France pseudo-labels, leaderboard feedback, or S2/S3 proxy were used.
- Entity IDs are used only for deterministic fit reconstruction, never as predictive evidence.
- No confirmation/frozen window was inspected.
- The Python normalizer is the same semantic NFD mirror used by X009 rather than byte-for-byte DuckDB `strip_accents`; reproducing fit count and the established 253/14 frequency maxima materially reduces but does not eliminate parity risk.
- This audits only anchor-side commonness. INT003 also has target-side frequency features, which require complete S2/S3 inventory access.
- Numeric distribution robustness is not an accuracy metric. A transform with worse KS could theoretically retrain well, but these two fail their preregistered purpose and should not be promoted as robustness fixes.

## Recommendation

**REJECT** both preregistered transforms as drop-in replacements for raw anchor frequency.

Do not spend a matcher training run on these exact formulas. A better follow-up is a split-size-stable representation that does **not** move the singleton mass with `country_rows`, such as train-defined frequency bins/quantiles or a clipped/raw-count hybrid whose cut points are fixed from labeled training and then applied unchanged at inference. Any such proposal must be retrained on the current INT003 candidate distribution and judged on existing development calibration/holdout only before consuming any new frozen window.

The X009 France address tail remains a real robustness concern; X010 rules out the tempting naive relative-frequency fix.
