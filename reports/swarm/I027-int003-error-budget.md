# I027 — INT003 confirmation error budget by stage

## Hypothesis

After INT003's confirmed character-retrieval gain, the remaining macro F0.5 deficit may be dominated by matcher/decision error rather than retrieval ceiling. An additive same-slice decomposition can identify where the current v3 pipeline still leaves the most score on the table without consuming another holdout.

## Change

No model, threshold, retriever, or challenge data changed. This is a committed-artifact forensic over:

- `reports/int003_depth10_confirmation.json`
- `reports/int003_depth10.json`
- `reports/swarm/INT003-character-fusion.md`

For any fixed candidate pool:

`1 - score = (1 - blocker_oracle) + (blocker_oracle - score)`

The first term is the score deficit imposed by missing candidates. The second is the shortfall of the actual matcher/decision rule relative to a perfect selector over the candidates that were retrieved.

## Protocol

Primary population: the already-consumed INT003 confirmation window, 5,000 Source-1 anchors at hash positions 45,001–50,000. No new challenge rows, labels, probabilities, confirmation/frozen windows, threshold tuning, or leaderboard feedback were inspected.

The v2 comparison uses the actual v2 model on its original lexical pool on these same 5,000 anchors. The frozen-v2-on-fused-pool diagnostic is also already committed in the confirmation artifact. Calibration and reused development holdout are included only as pre-existing stability context.

Singleton false-positive contribution is exact: under the official singleton convention, a true singleton scored with any nonempty prediction loses one full row score, so `singleton_FP_count / entity_count` is its absolute contribution to macro deficit.

## Results

### Current v3 confirmation budget

| Slice | Actual F0.5 | Oracle F0.5 | Total deficit | Retrieval deficit | Within-candidate deficit | Within-candidate share |
|---|---:|---:|---:|---:|---:|---:|
| All | 0.950198 | 0.980917 | 0.049802 | 0.019083 | 0.030718 | **61.68%** |
| India | 0.932699 | 0.970945 | 0.067301 | 0.029055 | 0.038246 | **56.83%** |
| US | 0.962081 | 0.987688 | 0.037919 | 0.012312 | 0.025607 | **67.53%** |

The residual within-candidate matcher/decision shortfall is larger than the retrieval-ceiling loss overall and in both labeled countries. Retrieval is still material: it accounts for 38.32% of the total confirmation deficit overall and 43.17% in India.

### What changed from v2 to v3 on the same 5,000 anchors

| Slice | Final score gain | Oracle gain / retrieval-loss reduction | Change in within-candidate deficit |
|---|---:|---:|---:|
| All | +0.007914 | +0.007988 | **+0.000075** |
| India | +0.010633 | +0.009573 | **-0.001060** |
| US | +0.006067 | +0.006912 | **+0.000845** |

At aggregate level, essentially all of the confirmed v2→v3 gain is explained by the higher retrieval ceiling. The within-candidate shortfall is nearly unchanged overall: 0.030644 for v2 on its original pool versus 0.030718 for v3 on the fused pool.

This does **not** mean retraining was unnecessary. Applying the frozen v2 model directly to the v3 fused candidate pool scored only 0.930872, leaving a 0.050044 within-candidate gap. Retraining on the fused pool recovered 0.019326 macro points of that gap overall; the recovery is 0.034351 in India and 0.009124 in the US. Retraining therefore absorbed the harder candidate distribution, but did not reduce the final residual decision gap below the old-pool v2 level.

### Singleton false-positive contribution

| Slice | Singleton FPs | Absolute macro deficit | Share of total deficit | Share of within-candidate deficit |
|---|---:|---:|---:|---:|
| All | 13 / 262 | 0.002600 | 5.22% | 8.46% |
| India | 8 / 114 | 0.003956 | 5.88% | 10.34% |
| US | 5 / 148 | 0.001679 | 4.43% | 6.56% |

Singleton false merges remain worth fixing, especially in India, but they are not the majority of the matcher/decision error budget. Even in India, about 89.7% of the within-candidate deficit lies outside these singleton false positives.

### Stability across already-committed development slices

The same qualitative decomposition holds on the existing v3 calibration and reused development holdout:

| Slice | Retrieval deficit | Within-candidate deficit | Within-candidate share |
|---|---:|---:|---:|
| Calibration, all | 0.019539 | 0.031340 | 61.60% |
| Holdout, all | 0.020700 | 0.034517 | 62.51% |
| Confirmation, all | 0.019083 | 0.030718 | 61.68% |
| Calibration, India | 0.030804 | 0.037509 | 54.91% |
| Holdout, India | 0.034005 | 0.048454 | 58.76% |
| Confirmation, India | 0.029055 | 0.038246 | 56.83% |
| Calibration, US | 0.012041 | 0.027234 | 69.34% |
| Holdout, US | 0.011931 | 0.025332 | 67.98% |
| Confirmation, US | 0.012312 | 0.025607 | 67.53% |

The near-identical overall shares across three already-committed slices make this unlikely to be a quirk of the 5,000-anchor confirmation composition.

## Error analysis

1. **Retrieval remains a hard structural ceiling.** V3 still loses 0.019083 macro points to missing candidates overall and 0.029055 in India. A perfect matcher cannot recover those links from the current pool.
2. **Matcher/decision now dominates the measured residual.** The 0.030718 within-candidate gap is 61.68% of the total confirmation deficit and is stable on calibration/holdout.
3. **Singleton precision is only one subproblem.** Exact singleton false positives explain 0.002600 macro points overall, 8.46% of the within-candidate gap. A singleton-only intervention cannot close most of the residual.
4. **V3's gain came from complementary retrieval, not a lower residual decision gap.** The fused pool raised the oracle by 0.007988 while the residual within-candidate gap changed by only +0.000075 overall.
5. **India improved in both stages.** Relative to v2-original-pool, India's retrieval deficit fell by 0.009573 and its within-candidate deficit fell by 0.001060. The US retrieval deficit fell by 0.006912, while its within-candidate deficit increased by 0.000845.

## Interpretation

The next integration cycle should not treat retrieval as the only bottleneck merely because the historical blocker oracle was the headline constraint. INT003 removed a meaningful chunk of retrieval loss, and the measured residual is now larger inside the retrieved candidate set.

The highest-value matcher/decision follow-ups are therefore those that attack ambiguity and set selection across **non-singleton as well as singleton** anchors: hard-negative discrimination, richer pair evidence, score-gap/ambiguity features, source-aware decisions, and calibrated set selection. Retrieval work remains justified, particularly for India, but an additional oracle gain has to be converted by a matcher that already leaves about 0.031 macro points on the table within the current pool.

## Risks

- This is an additive score-gap decomposition, not a causal counterfactual. Changing retrieval can also change matcher difficulty and calibration, as the frozen-v2-on-fused-pool result demonstrates.
- The blocker oracle assumes perfect selection among retrieved candidates; it does not identify which matcher feature or decision rule causes the remaining gap.
- Singleton-FP contribution is exact for that failure family, but the residual cannot be subdivided into FP/FN/cardinality mechanisms without per-anchor prediction artifacts.
- France has no labels, so none of these score shares establish French performance.
- Confirmation 45,001–50,000 is already consumed; no tuning decision should be fit to it.

## Recommendation

**FOLLOW-UP.** Preserve INT003. Rebalance the next research wave toward matcher/decision experiments because they account for about 62% of the current labeled confirmation deficit, while continuing targeted retrieval work because the remaining oracle loss is still about 0.019 overall and 0.029 in India.

Do not over-focus on singleton gating alone: exact singleton false positives are only 8.46% of the within-candidate deficit overall and 10.34% in India. The larger opportunity is ambiguity/cardinality discrimination among retrieved non-singleton candidate sets.
