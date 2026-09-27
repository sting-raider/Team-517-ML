# D022 — Calibration-only country-conditioned neural32 decision variant

## Hypothesis

The cap32 neural32 matcher may need different decision calibration by country because India and US have materially different error profiles. Selecting among the already-committed INT006 top-level variants independently for India and US using **calibration-country macro F0.5 only** may improve the official per-anchor macro F0.5 without changing retrieval or introducing new model inference.

## Change

No production code, candidates, or scores were changed.

Using `reports/capped_match_evaluation.json` from `integration/int005-learned-retrieval`, D022 selected the best existing top-level variant separately for India and US by that country's calibration macro F0.5. Each candidate variant retained its already calibration-selected threshold. The untouched holdout country metrics were then combined by exact entity-count weighting, which is valid because the official metric is a macro average over Source-1 anchors.

Variants considered were exactly the existing committed INT006 top-level variants:
- `cross_only`
- `dense_prior_-2`
- `dense_prior_-1`
- `dense_prior_0`
- `dense_prior_1`

No dense-gate sweep parameter was added to this experiment, avoiding overlap with D009a.

## Protocol

- Base ref: `integration/int005-learned-retrieval`
- Candidate pool: frozen INT006 cap32
- Calibration: 4,389 anchors
  - India: 1,754
  - US: 2,635
- Holdout: 3,051 anchors
  - India: 1,212
  - US: 1,839
- Selection criterion: maximum **country calibration macro F0.5**
- Holdout was not used to select country, variant, prior, or threshold.
- No confirmation block, public leaderboard feedback, France labels/pseudo-labels, external identity data, new retrieval, new model inference, or raw challenge rows were used.
- Source artifact: `reports/capped_match_evaluation.json`

## Results

### Selected rule by country

| Country | Calibration-selected variant | Dense prior | Threshold | Calibration macro F0.5 | Holdout macro F0.5 |
|---|---|---:|---:|---:|---:|
| India | `dense_prior_-2` | -2.0 | 0.95 | 0.976022816 | 0.968359654 |
| US | `dense_prior_-1` | -1.0 | 0.875 | 0.978631749 | 0.974145535 |

The globally selected INT006 V5 rule is `dense_prior_-2`, threshold 0.95.

### Aggregate comparison

| Metric | Global V5 | Country-conditioned | Delta |
|---|---:|---:|---:|
| Calibration macro F0.5 | 0.977237614 | 0.977589127 | +0.000351513 |
| Holdout macro F0.5 | 0.970702114 | 0.971847112 | **+0.001144998** |
| India holdout macro F0.5 | 0.968359654 | 0.968359654 | +0.000000000 |
| US holdout macro F0.5 | 0.972245922 | 0.974145535 | **+0.001899613** |

US singleton FPR changes from **3.9216%** under the global `dense_prior_-2` rule to **4.9020%** under the calibration-selected `dense_prior_-1` rule. India remains at **8.2474%** because its selected rule is unchanged.

Candidate retrieval diagnostics are unchanged by construction:
- holdout candidate pair recall: **0.978484387**
- holdout candidate entity recall: **0.977614985**
- holdout all-matches-retrieved rate: **0.928471248**
- holdout blocking oracle macro F0.5: **0.992823037**
- candidate cap: **32**

## Error analysis

1. **Gain is entirely US-side.** India calibration independently selects the existing global V5 rule, so this experiment does not address the remaining India weakness.
2. **US trades some singleton precision for macro gain.** The selected US rule raises singleton FPR by about 0.98 percentage points while improving US macro F0.5 by about 0.00190.
3. **The calibration signal is directionally consistent.** US calibration prefers `dense_prior_-1` over the global `dense_prior_-2`, and the same rule improves US holdout. This is stronger than selecting on holdout, but the absolute delta is still small.
4. **No retrieval benefit is involved.** All candidate recall/oracle values are identical. The mechanism is purely country-conditioned decision calibration.
5. **The experiment is conservative in scope.** It does not search new country-specific thresholds. It only reuses complete pre-existing variants, reducing degrees of freedom.

## Red-team checks

- **Holdout leakage:** none in selection. Country rules were selected from calibration-country macro F0.5 only.
- **Candidate-cap mismatch:** none. Every compared row uses the same frozen cap32 candidate set.
- **Retrieval mismatch:** none. Candidate recall and oracle metrics are identical.
- **Threshold retuning on holdout:** none.
- **Sampling mismatch:** none. Exact committed calibration and holdout country anchor counts were used.
- **Metric composition:** combined score is exact entity-count weighting of disjoint India/US macro scores, equivalent to per-anchor macro over the union.
- **Repeated-holdout risk:** material. This holdout has already been used extensively by the swarm, so the +0.001145 should not be treated as independent confirmation.

## Interpretation

Country conditioning appears useful for the current neural32 decision layer, but the measured benefit is modest and entirely US-driven. The strongest evidence is that the calibration-only selector chooses a different US rule and that this direction persists on holdout.

This does **not** solve the India gap. A higher-value follow-up would test a genuinely India-specific decision feature or calibration family on a fresh admissible split rather than widening the same prior grid.

## Risks

- Small absolute gain on a reused holdout.
- The selected US rule increases singleton FPR.
- France has no labels; country-specific India/US rules do not establish a France-safe policy.
- This aggregate-only experiment cannot provide paired-anchor bootstrap significance because committed artifacts do not include per-anchor scores for every variant.
- Production integration would require an explicit policy for unseen countries rather than silently mapping France to either India or US.

## Recommendation

**REPLICATE.**

The calibration-only mechanism is coherent and the holdout direction is favorable, but +0.001145 on a repeatedly inspected holdout is not sufficient for production promotion. Replicate on a fresh admissible labeled split or future coordinator gate. If replicated, implement country-conditioned decision configuration with an explicit language-agnostic/default fallback for unseen France rather than applying a US/India rule by assumption.

## Follow-up

1. Replicate D022 on the next fresh labeled integration gate using the exact two-country rule above, with no retuning.
2. Keep India-focused decision work separate: D022 found no India improvement.
3. If D022 replicates, evaluate an explicit unseen-country fallback before any France/test export.
