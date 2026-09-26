# M015 — anchor-balanced CatBoost training weights

## Hypothesis

The official score is an equal-weight macro F0.5 over Source-1 anchors, while a pairwise matcher sees candidate rows. The preregistered concern was that current INT003 training might therefore give anchors with more candidate rows more total CatBoost loss weight. If true, per-anchor-normalized row weights could better align training with the official metric.

## Change

No production matcher change is recommended. Source audit on latest `main` (`f08c041b274e58ae900620ac714ec8a0a06f09b0`) found that `src/ber/v2.py::train()` already computes inverse candidate-count weights for fit rows:

```python
counts=np.bincount(groups,minlength=len(meta))
weights=1/np.maximum(1,counts[groups[fit]])
weights/=weights.mean()
model.fit(..., sample_weight=weights, ...)
```

`modal_v3.py::train_model()` imports and calls this exact `ber.v2.train()` function for the 57-feature INT003 model. Thus every fit anchor with at least one candidate row already contributes the same total row-weight mass. M015 adds only a dependency-light audit helper and focused tests so this negative result is reproducible.

## Protocol

Data: complete supplied `train_source1.tsv` and `train_ground_truth.tsv`, no sampling. The helper reproduces repository `fold517` and INT003's deterministic Source-1 ordering by `md5('sample517:' || entity_id)`, retains the first 200,000 positions, and reconstructs the actual fit window: fit-fold anchors at positions 1–30,000 and 50,001–200,000. IDs are used only for deterministic split reproduction, never as predictive evidence.

Command:

```bash
python tools/experiments/m015_anchor_weight_audit.py \
  --source1 /path/to/train_source1.tsv \
  --truth /path/to/train_ground_truth.tsv \
  --out reports/swarm/M015-anchor-balanced-training.json
python -m unittest tests/test_m015_anchor_weight_audit.py -v
```

Runtime in this ChatGPT container: CPython 3.13.5, 12.17 s for the complete 2,206,821-anchor audit; focused tests 4/4 PASS. No Source-2/3 records, candidate probabilities, confirmation/frozen holdout, France labels, leaderboard feedback, or external entity data were used.

## Results

The reconstruction exactly reproduces committed INT003 selection totals: **108,115 fit anchors**, comprising **64,955 US** and **43,160 India**. As an additional parity check, the first 30,000 Source-1 positions reproduce **17,990 fit / 4,570 early / 4,389 calibrate / 3,051 holdout**, matching the committed calibration and holdout populations.

| Quantity | Full labeled population | INT003 fit population | Fit minus population |
|---|---:|---:|---:|
| Anchors | 2,206,821 | 108,115 | — |
| Mean truth cardinality | 3.461253 | 3.462665 | +0.001412 |
| Empty-truth rate | 5.584821% | 5.521898% | -0.062923 pp |
| One-match rate | 5.399486% | 5.483050% | +0.083564 pp |
| 2+ match rate | 89.015693% | 88.995052% | -0.020641 pp |
| 5+ match rate | 26.021549% | 26.000092% | -0.021456 pp |

The empty-truth standardized difference is **-0.00274** and the 5+ standardized difference is **-0.00049**, both negligible. The fit sample therefore does not show a meaningful cardinality-composition distortion that would revive the original weighting concern.

INT003 reports 16,043,969 fit candidate rows, or **148.397 candidate rows per selected fit anchor on average**. Regardless of that row-count variation, the existing inverse-count formula is exact: for anchor `g` with `n_g > 0` candidate rows, its summed normalized weight is `n_g * (1/n_g) / mean_raw = 1/mean_raw`, independent of `n_g`.

## Error analysis

The original failure mode is absent on current main. Two distinct issues remain, but neither justifies another anchor-normalization layer:

1. An anchor with zero retrieved candidates has no pair rows and therefore cannot contribute to pairwise training at all. The private fit candidate arrays are not available in this runtime, so M015 does not remeasure zero-candidate prevalence. This is fundamentally a retrieval/data-coverage issue, not a row-weight normalization bug.
2. Equal anchor mass does not make pairwise Logloss identical to set-valued macro F0.5. Within an anchor, positive/negative class balance varies with retrieved truth cardinality, and F0.5 is nonlinear and precision-heavy. That remaining objective mismatch belongs to calibrated set decoding / expected-F0.5 work, not a duplicate inverse-count weight.

## Risks / red-team checks

- Full Source-1 and truth populations were used; no sample surrogate.
- The exact INT003 fit count and country counts reproduce prior committed audits, reducing risk of split-semantic drift.
- The 30k fold counts independently reproduce the known 4,389 calibration and 3,051 holdout counts.
- No confirmation/frozen window was evaluated or tuned.
- No candidate/model score is claimed because private fit candidate arrays and model artifacts were not available here.
- The audit does not claim that CatBoost Logloss is F0.5-optimal; it only falsifies the narrower unequal-anchor-mass premise.

## Recommendation

**REJECT / SUPERSEDED.** Do not implement or empirically gate a second per-anchor inverse-count weighting scheme: INT003 already uses it. Preserve the current weighting invariant and spend matcher/decision effort on genuinely distinct mechanisms such as hard-negative quality, calibrated probabilities, candidate-interaction evidence, or expected-F0.5/set-level decoding.

No production model behavior changes are proposed by this PR.
