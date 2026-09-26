# M016 — anchor-balanced CatBoost early-stopping evaluation

## Hypothesis

INT003 already equalizes **fit-loss** mass across Source-1 anchors, but `ber.v2.train()` passes the early-stopping set as an unweighted `(X, y)` tuple. CatBoost uses the validation set for best-iteration / overfitting decisions, so an early anchor with more candidate rows can receive more validation-metric mass than an anchor with fewer rows. This can make tree-count selection depend on candidate multiplicity even though the training objective itself is anchor-balanced.

## Change

No production training behavior is changed in this branch. M016 adds a deterministic CatBoost 1.2.8 synthetic stress test plus unit tests and documents the exact one-variable private-data gate required before changing INT003 training.

Latest-main source audit (`f08c041b274e58ae900620ac714ec8a0a06f09b0`):

```python
counts=np.bincount(groups,minlength=len(meta))
weights=1/np.maximum(1,counts[groups[fit]])
weights/=weights.mean()
model.fit(
    x[fit], y[fit],
    sample_weight=weights,
    eval_set=(x[early],y[early]),
    early_stopping_rounds=120,
)
```

The fit rows are anchor-balanced; the early rows are not. `modal_v3.py::train_model()` calls this exact `ber.v2.train()` implementation for INT003.

CatBoost's official Python API documents that `eval_set` is used for the overfitting detector and best-iteration selection, that `eval_set` may be a `Pool`, and that `Pool` supports per-object weights. CatBoost metric documentation states that object weights are used when weights are present for weighted metrics such as Logloss. References: `catboost.ai/docs/en/concepts/python-reference_catboostclassifier_fit`, `python-reference_pool`, and `loss-functions`.

## Protocol

Synthetic test only; no challenge rows or labels are used.

- CatBoost 1.2.8, CPU, seed 517.
- Fixed 3,000-row learn set with a learnable binary relation.
- Validation contains 20 conceptual anchors.
- Nineteen ordinary anchors have ten rows each.
- The twentieth anchor is deliberately contradictory to the learnable relation, so deeper fitting worsens its Logloss.
- The evidence for that hard anchor is held constant; only the number of duplicate validation rows is changed from 1 to 190.
- Compare an ordinary unweighted `(X, y)` validation tuple against a `Pool` whose row weights are inverse candidate count within each conceptual anchor and globally mean-normalized.
- All model hyperparameters and training data remain identical.

Command:

```bash
python tools/experiments/m016_early_stop_weight_probe.py \
  --out reports/swarm/M016-balanced-early-stop.json
python -m unittest tests/test_m016_early_stop_weight_probe.py -v
```

Synthetic helper runtime: 3.57 s. Focused tests: 3/3 PASS in 1.35 s.

## Results

| Validation construction | Hard-anchor rows | Validation rows | Best iteration | Saved trees | Best Logloss |
|---|---:|---:|---:|---:|---:|
| Unweighted tuple | 1 | 191 | 40 | 41 | 0.228372 |
| Unweighted tuple | 190 | 380 | 0 | 1 | 0.746713 |
| Anchor-balanced Pool | 1 | 191 | 13 | 14 | 0.3984432903 |
| Anchor-balanced Pool | 190 | 380 | 13 | 14 | 0.3984432892 |

Changing only the duplicate row count of one validation anchor moved the unweighted best iteration **40 → 0**. With inverse-count validation weights, best iteration stayed **13 → 13** and best Logloss matched to about 1e-9. The weighted validation metric is therefore invariant to this pure row-multiplicity perturbation, while the current tuple semantics are not.

This is a **mechanism proof**, not an INT003 score claim. The synthetic case is deliberately adversarial to make the weighting effect observable. Real INT003 candidate counts may be sufficiently concentrated near cap 160 that the practical difference is small.

## Error analysis / limitations

- M016 does not have the private INT003 fit/early candidate arrays, so it cannot measure the actual early-anchor candidate-count distribution or retrain the real model here.
- The committed INT003 retrieval gate reports median candidate count 160 and mean 148.05 on calibration, suggesting many anchors are near the cap, but that is not the early fold and does not eliminate the mismatch.
- Anchor-balanced early Logloss is still not the official set-valued macro F0.5. This change only aligns **anchor mass**, not the nonlinear set decision objective.
- Validation weighting must not be confused with training sample weights; the fit path is already correct on that narrower invariant (M015).
- No confirmation/frozen holdout may be reused to decide this variant.

## Private empirical gate

Run exactly one paired INT003 development experiment on the existing private feature arrays:

1. Keep candidate pool, 57 features, fit rows, fit weights, seed 517, depth 10, learning rate, L2, and iteration budget unchanged.
2. Baseline: current unweighted `eval_set=(x[early], y[early])`.
3. Variant: build `early_weights = 1 / early_candidate_count[groups[early]]`, mean-normalize it, and pass `Pool(x[early], y[early], weight=early_weights)` as the single eval set.
4. Recalibrate threshold on the same calibration fold for each model, as required after tree-count changes.
5. Compare on the same calibration and reused development holdout: macro F0.5, India/US, singleton FPR, tree count, threshold, pair recall (must be unchanged), runtime.
6. Do not touch the consumed 45,001–50,000 confirmation window. Escalate to a coordinator-controlled fresh confirmation only if the paired development effect is material and stable.

## Recommendation

**FOLLOW-UP.** The current early-stopping path has a real anchor-mass inconsistency that CatBoost weighted `Pool` evaluation can remove. The synthetic effect is strong enough to justify one private paired gate, but there is no evidence yet that it improves real macro F0.5, so changing production training now would be premature.
