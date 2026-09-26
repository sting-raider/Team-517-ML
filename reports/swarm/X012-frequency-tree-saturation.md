# X012 — CatBoost saturation audit for the France frequency tail

## Scientific question

X009 found that 989 / 259,452 France Source-1 anchors (0.3812%) have raw normalized-address frequency above the maximum observed by the selected matcher's 108,115 fitting anchors: frequency 14, or `ln(15)=2.70805`. France reaches frequency 101, or `ln(102)=4.62497`.

Does that high-side numeric tail create a genuinely new INT003 model state, or does the frozen CatBoost model map every value above the learn maximum into the same terminal numerical bucket as the maximum learn value?

## Scope and source audit

No challenge rows or labels are newly inspected in this task. The X009/X010 aggregate support facts are treated as already-measured inputs.

Latest-main source establishes:

- `src/ber/v2.py` constructs a plain float feature matrix and trains `CatBoostClassifier` on `x[fit]`.
- the early-stop split is supplied only as `eval_set=(x[early], y[early])`;
- no categorical feature indices or custom numerical borders are supplied;
- `src/ber/v3.py` extends `V2_NAMES` by four more numeric retrieval-channel features and delegates materialization/training to the v2 path.

Therefore `log_anchor_name_frequency` and `log_anchor_address_frequency` are ordinary numerical CatBoost inputs.

Official CatBoost documentation states that numerical features are quantized into disjoint ranges separated by learned borders, and that the validation dataset is used for evaluating training quality rather than training. It also documents saving quantization borders from the training dataset and reusing those borders for evaluation data:

- https://catboost.ai/docs/en/concepts/quantization
- https://catboost.ai/docs/en/concepts/algorithm-main-stages
- https://catboost.ai/docs/en/concepts/python-reference_save_quantization_borders

## Focused executable check

Added `tests/test_x012_catboost_saturation.py`.

The synthetic test deliberately:

1. trains a numerical CatBoost classifier whose learn support for feature 0 is 1..100;
2. supplies validation-only feature-0 values 1000, 2000, and 5000;
3. checks `model.get_borders()[0]` remains strictly inside the learn support;
4. holds a second interacting feature fixed and verifies predictions are bit-identical at 100, 101, 1000, and 1e9.

Runtime environment: CatBoost 1.2.8, CPU.

Validation:

```
test_auto_borders_stay_inside_learn_support ... ok
test_values_above_learn_max_share_prediction_for_fixed_context ... ok

Ran 2 tests in 0.087s
OK
```

Observed synthetic maximum feature-0 border: 94.5 while learn maximum is 100.0. Values 100, 101, 1000 and 1e9 returned exactly identical probabilities for each fixed value of the interacting context feature.

## Result

**PROMOTE the interpretation correction; do not add a production clipping patch.**

For a frozen tree model whose numerical borders were learned from a learn set with maximum value `M`, every finite value `x >= M` has the same result against every learned numerical border as `M`. It therefore enters the same quantized bucket and traverses the same tree branches, holding all other features fixed.

Applied to the measured INT003 anchor-address feature:

- fitting-anchor maximum raw frequency = 14;
- maximum learn feature value = `ln(15)=2.70805`;
- France's 989 high-side rows with frequency >14 are above that maximum;
- those rows cannot create a new high-side CatBoost bucket in the frozen model;
- explicitly clipping their feature value to `ln(15)` would be prediction-equivalent for this feature, provided the actual v3 model uses the auto-generated learn borders shown by the source path.

This sharply narrows X009's risk statement. The France tail is still evidence that France has a different address-collision regime, but it is **not direct linear-style numeric extrapolation** by the frozen INT003 matcher.

## What remains a real robustness concern

This result does **not** establish France accuracy and does not make all frequency drift irrelevant.

Still material:

- distribution movement **inside** the learned border range can change bucket membership;
- frequency may correlate with other shifted name/address evidence even when its own high-side value saturates;
- INT003 also has target-side name/address frequencies; X009/X010 audited only anchor-side features;
- a future retrained model could learn different borders if its fitting population or feature transform changes;
- no France labels exist, so no France F0.5 claim is possible.

X010 independently showed that naive country-size normalization is worse: it moves the dominant singleton value and increases France address out-of-fit numeric support from 0.3812% raw to 4.1638%. X012 explains why a raw high-side clip is not needed for the already-frozen tree model.

## Red-team / limitations

- No raw S2/S3 substitution, pseudo-labels, confirmation/frozen-window reuse, leaderboard feedback, or external entity identity data.
- The private INT003 `mixed.cbm` is not available in this chat runtime, so its exact saved border list was not directly dumped.
- The executable test uses CatBoost 1.2.8 CPU, while INT003 was trained on GPU. CPU/GPU differ in default border counts, but the audited property is the shared numerical-bucket semantics, not the exact number of borders.
- Exact private-model closure is cheap if a coordinator has the private artifact: load the v3 model, call `get_borders()`, and verify the two anchor-frequency border maxima are below the measured fit maxima. This is an integrity confirmation, not a tuning run.

## Recommendation

**PROMOTE** this as a planning correction:

1. do not prioritize clipping the current raw anchor-frequency tail as a frozen-model France fix;
2. keep X009's France collision-regime finding as a distributional warning, not a claim of tree extrapolation;
3. spend robustness effort on evidence that can actually move tree buckets or candidate decisions: within-support frequency drift, target-side commonness, ambiguity/singleton evidence, and retrieval misses.

No production model or submission behavior changes in this task.
