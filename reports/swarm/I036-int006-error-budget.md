# I036 — INT006/V6 retrieval-vs-matcher error budget

## Hypothesis

INT006's neural blocker moves enough true links into a much smaller cap-32 candidate set that the dominant remaining holdout loss may have shifted from retrieval to matcher/decision error. Quantifying that shift matters because the pre-INT006 retrieval-first priority should not be carried forward by habit after the measured system changes.

## Change

No production behavior changes. This task adds a deterministic aggregate-only decomposition helper and applies it to the exact same 3,051-anchor development holdout metrics already recorded for selected INT003 (v3), INT006/V5, and INT007/V6.

For score `S` and blocking oracle `O`, the identity is:

- total deficit from perfection: `1 - S`
- retrieval ceiling loss: `1 - O`
- within-candidate matcher/decision loss: `O - S`

These sum exactly. The split is descriptive, not a causal counterfactual: changing retrieval can change candidate difficulty and therefore matcher behavior.

## Protocol

Upstream evidence is frozen to draft PR #268 head `fdff7866c4419f4fb645aa8d45a2a15696b8b729` plus latest-main `reports/int003_depth10.json`.

Inputs:

- INT003 selected holdout: `reports/int003_depth10.json`, `new.holdout`
- INT006 selected V5 variant: PR #268 `reports/capped_match_evaluation.json`, variant `dense_prior_-2`, `holdout`
- INT007/V6 overall score: PR #268 `reports/swarm/INT007-blank-address-recovery.md`, reported `0.972095`; V6 uses the unchanged V5 candidate file, so its blocking oracle is identical
- target diagnostic: `0.998`

Reproduction after making both upstream JSON files available locally:

```bash
python tools/experiments/i036_int006_error_budget.py \
  --v3-json /path/to/int003_depth10.json \
  --v5-json /path/to/capped_match_evaluation.json \
  --v5-variant dense_prior_-2 \
  --v6-score 0.972095 \
  --output reports/swarm/I036-int006-error-budget.json
python -m unittest tests.test_i036_int006_error_budget -v
```

No challenge rows, labels, candidate probabilities, confirmation/frozen windows, France labels, external data, or leaderboard feedback are consumed. This analysis does **not** independently validate PR #268; I035 owns that broad red-team task.

## Results

### Current V5/V6 stage budget

| Holdout slice | Realized F0.5 | Oracle F0.5 | Total deficit | Retrieval loss | Within-candidate loss | Within-candidate share |
|---|---:|---:|---:|---:|---:|---:|
| V5 all | 0.970702 | 0.992823 | 0.029298 | 0.007177 | 0.022121 | **75.50%** |
| V5 India | 0.968360 | 0.991419 | 0.031640 | 0.008581 | 0.023060 | **72.88%** |
| V5 US | 0.972246 | 0.993748 | 0.027754 | 0.006252 | 0.021502 | **77.47%** |
| V6 all | 0.972095 | 0.992823 | 0.027905 | 0.007177 | 0.020728 | **74.28%** |

The same-candidate V6 rule gains +0.001393 over V5 and closes about **6.30%** of V5's measured oracle-to-score gap. Even after that recovery, about three quarters of the remaining measured deficit is inside the candidate set rather than imposed by retrieval.

### What changed from INT003 v3 to neural32 V5

On the exact same holdout, v3 scored 0.944783 with oracle 0.979300. V5 scores 0.970702 with oracle 0.992823, a +0.025919 realized gain.

That gain decomposes algebraically into:

- +0.013523 from raising the candidate oracle, **52.17%** of the realized gain;
- +0.012396 from shrinking the oracle-to-realized gap, **47.83%**.

India is almost exactly 50/50: +0.025424 oracle gain and +0.025395 within-candidate gap reduction produce the +0.050819 realized gain. US is more retrieval-led in the transition, with +0.005679 oracle gain versus +0.003829 gap reduction.

So neural32 succeeded because it improved both stages, not because one stage alone explains the jump.

### Consequence for the 0.998 aspiration

The current cap-32 holdout oracle is **0.992823**, which is **0.005177 below 0.998**. Therefore 0.998 is mathematically impossible on this holdout with the current candidate set even under a perfect matcher.

To make an oracle of 0.998 merely possible, retrieval would need to remove **72.13% of its current F0.5 ceiling loss** (`0.005177 / 0.007177`). That is a score-ceiling statement, not a pair-recall percentage. Reaching an oracle of exactly 0.998 would also leave zero room for matcher mistakes, so a practical 0.998-capable system needs an oracle above 0.998 and a much smaller oracle-to-realized gap.

India is more constrained: its V5 oracle is 0.991419, so it needs +0.006581 oracle points just to reach 0.998, corresponding to **76.69%** of its current retrieval-imposed loss. US needs +0.004252, or **68.01%** of its current retrieval-imposed loss.

## Error analysis / interpretation

The priority has shifted, not disappeared. Under v3, retrieval accounted for 37.49% of the overall deficit from 1.0; under V5 it accounts for 24.50%. Within-candidate error now accounts for 75.50% overall and remains above 72% in both labeled countries.

This makes matcher/decision work the larger immediate measured headroom on the current neural32 pool. Candidate-score calibration, hard neural-only decisions, exact-evidence overrides like INT007, and set-level decoding deserve more attention than another indiscriminate candidate widening pass. The INT006 report already shows the mechanism: selected neural-only links have much lower pair precision than lexical/character links, especially India, while lexical/character selected links are near 99.6% precision.

Retrieval is still structurally mandatory for the 0.998 aspiration because the oracle itself is below target. The sensible next retrieval work is therefore selective recovery that lifts oracle without destroying the cap-32 candidate-quality regime, not a return to large uniform candidate budgets.

## Risks

- The 3,051-anchor development holdout has been reused across experiments. Treat magnitudes as planning evidence, not a fresh generalization estimate.
- V6's committed report rounds its overall score to six decimals; its decomposition therefore has corresponding rounding error. V5/v3 values come from exact JSON.
- The additive identity is a loss accounting device, not proof that independent stage improvements will add linearly after retraining.
- France has no labels. Nothing here establishes the same error proportions on France or the leaderboard.
- PR #268 is still draft and under independent I035 red-team. If its reported candidate or evaluation semantics are invalidated, this prioritization analysis must be revisited.

## Recommendation

**PROMOTE-DIAGNOSTIC / FOLLOW-UP.** Update swarm prioritization for the neural32 candidate pool: matcher/decision error is now the larger measured loss bucket, while retrieval remains a hard ceiling that must improve for 0.998 to be possible. Prefer high-precision within-candidate fixes and selective oracle-lifting retrieval, especially India, over broad candidate expansion.
