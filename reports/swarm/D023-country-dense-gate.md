# D023 — Country-conditioned neural32 dense-gate sweep

## Hypothesis

D009a found that an extra penalty on dense-only candidates improves the neural32 decision layer. Because India remains weaker than the US, the optimal extra penalty might differ by country. Selecting the already-committed dense-gate penalty independently for India and US using calibration-country macro F0.5 could improve holdout macro F0.5 without changing retrieval.

## Change

No production code, candidate membership, model scores, or thresholds changed.

D023 reuses the committed `dense_gate_sweep` from `reports/capped_match_evaluation.json`, keeping:
- base V5 dense prior = -2
- base threshold = 0.95
- exact cap32 candidate pool

For each country independently, the extra dense-only logit penalty was selected strictly by that country's calibration macro F0.5.

## Protocol

- Base ref: `integration/int005-learned-retrieval`
- Calibration: 4,389 anchors
  - India 1,754
  - US 2,635
- Holdout: 3,051 anchors
  - India 1,212
  - US 1,839
- Candidate cap: 32
- Candidate pool and retrieval diagnostics fixed
- Existing penalty grid only: -1, 0, 0.5, 1, 1.5, 2, 3
- No holdout-driven selection, no new inference, no confirmation data, no leaderboard feedback, no France labels/pseudo-labels, no external identity data

## Results

### Calibration-selected country gates

| Country | Selected extra dense penalty | Calibration macro F0.5 | Holdout macro F0.5 | Holdout singleton FPR |
|---|---:|---:|---:|---:|
| India | +0.5 | 0.977392681 | 0.968682810 | 8.2474% |
| US | +1.0 | 0.978191930 | 0.973592395 | 1.9608% |

D009a's globally selected gate is **+0.5**.

### Aggregate comparison

| Rule | Calibration macro F0.5 | Holdout macro F0.5 | Delta vs previous |
|---|---:|---:|---:|
| V5, no extra gate | 0.977237614 | 0.970702114 | — |
| Global D009a gate +0.5 | 0.977844004 | 0.971448671 | +0.000746557 vs V5 |
| Country-conditioned gate | 0.977872521 | 0.971642078 | **+0.000193407 vs global gate** |

Against V5, the country-conditioned gate is +0.000939964 on holdout.

Country detail versus the global +0.5 gate:
- India: **no change**, because calibration selects the same +0.5 penalty.
- US: 0.973271523 → 0.973592395, **+0.000320872**.
- US singleton FPR remains 1.9608% for both +0.5 and +1.0 in the committed aggregate report.

Retrieval is unchanged:
- holdout candidate pair recall: 0.978484387
- holdout candidate entity recall: 0.977614985
- all-matches-retrieved rate: 0.928471248
- blocking oracle macro F0.5: 0.992823037

## Error analysis

1. **No India-specific gain.** India independently selects the same +0.5 gate already selected globally.
2. **The extra country complexity buys only a tiny US gain.** +0.0003209 US and +0.0001934 overall versus the global gate.
3. **Precision behavior does not improve further.** The US singleton FPR is identical between the global and country-selected gates in the committed aggregate output.
4. **The result is fully decision-only.** Candidate recall/oracle values are identical by construction.
5. **The relative ranking is calibration-consistent**, but the magnitude is too small for confident promotion on a heavily reused holdout.

## Red-team checks

- Selection uses calibration-country macro F0.5 only.
- Holdout is evaluation only.
- Exact same candidate cap and candidate membership.
- Same V5 base prior and threshold for every penalty.
- No new threshold search.
- Exact country entity counts used for weighted macro composition.
- No France assumptions.
- No candidate IDs used as predictive features.
- Reused-holdout risk remains significant.

## Interpretation

Country-specific dense gating does not address the India problem. The globally selected +0.5 penalty is already the India optimum on calibration. Letting the US use +1.0 adds only +0.000193 overall versus the global gate.

This is useful negative knowledge: further complexity in this one-dimensional dense-only penalty family is unlikely to be a high-value India path.

## Risks

- Holdout has been repeatedly inspected by the swarm.
- Delta versus the global gate is very small.
- Aggregate artifacts do not support paired-anchor uncertainty analysis.
- A country-conditional production policy adds France fallback complexity for negligible measured benefit.

## Recommendation

**REJECT as a separate production rule; retain D009a global gate as the simpler candidate.**

The +0.000193 holdout improvement over D009a does not justify country-specific branching, and it produces no India gain. Future India decision work should use a different mechanism rather than a finer split of the same dense-only penalty.

## Follow-up

- Do not spend another experiment widening this penalty grid by country.
- Prioritize India-specific error features, set-level decisions, or matcher calibration mechanisms that can move the India slice rather than merely the US slice.
