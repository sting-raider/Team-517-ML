# M006a — Wide-cap hard-negative training distribution gap

**Issue:** #70  
**Branch:** `agent/m/M006a-wide-negative-gap`  
**Baseline audited:** main `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`  
**Recommendation:** FOLLOW-UP with a matched wide-negative retraining experiment

## Hypothesis

The selected depth-10 CatBoost matcher is trained on candidate rows generated with the original cap-80 blocker, then evaluated and deployed on substantially wider cap-160/640 candidate pools. If the newly exposed lower-ranked candidates are overwhelmingly negatives, the matcher is being asked to reject a distribution of hard negatives that was largely absent from training.

That mismatch can waste retrieval-oracle gains and is a direct motivation for M006 hard-negative mining.

## Change

No model behavior was changed. This is a Tier-0 forensic audit using the committed training code and aggregate experiment artifacts.

## Protocol

Inspected:

- `src/ber/blocking.py`
- `src/ber/experiment.py`
- `src/ber/tune.py`
- `src/ber/wide_evaluate.py`
- `src/ber/candidate_budget.py`
- `reports/address_baseline.json`
- `reports/wide_calibration.json`
- `reports/tuning.json`
- `reports/candidate_budget.json`

For the exact calibration population, I also cross-checked the independently reproduced aggregate truth count from I001 (`agent/i/I001-fast-benchmark`): **4,389 anchors, 252 singletons, 15,276 positive links**. I001 obtained those counts from the complete raw Source-1 and ground-truth TSVs.

No new confirmation/frozen holdout was consumed. This chat's Python/container pool is unavailable and the complete S2/S3 files exceed the Drive connector's 256 MiB transfer ceiling, so no fresh CatBoost retraining result is claimed.

## Results

### 1. The selected matcher is trained on cap-80 candidates

The original development pipeline builds `artifacts/address_baseline/features.npz` from the default blocker cap of **80**.

`tune.py` loads that artifact as its only labeled training matrix:

- `x, y, groups` come from `artifacts/address_baseline/features.npz`;
- CatBoost fit rows are only the `fit` anchors in that matrix;
- CatBoost early-stopping rows are only the `early` anchors in that matrix.

The wide artifact is different:

- `artifacts/wide_calibration/features.npz` contains only **calibration** anchors;
- it is used for depth/threshold evaluation, not model fitting.

Therefore the selected depth-10 model never trains on rank-81-to-640 candidate negatives.

**Finding: confirmed training/deployment candidate-distribution mismatch.**

### 2. The cap-80 training artifact is much less negative-heavy than the marginal wide pool

`reports/address_baseline.json` records, over the 30,000-anchor cap-80 development artifact:

- candidate pairs: **2,252,063**
- positive candidate pairs: **94,955**
- candidate-positive fraction: **4.216%**

This is the full cap-80 development artifact rather than the fit subset alone, but it is the exact artifact family from which `tune.py` selects fit/early rows.

On the fixed 4,389-anchor calibration slice, the committed depth-10 candidate-budget results imply:

| Cap | Mean candidates | Approx total candidates | Pair recall | Approx retrieved true links |
|---:|---:|---:|---:|---:|
| 80 | 74.91 | 328,773 | 0.912150 | 13,934 |
| 160 | 142.18 | 624,037 | 0.925308 | 14,135 |
| 640 | 442.63 | 1,942,700 | 0.945863 | 14,449 |

The retrieved-true-link counts use the independently reproduced **15,276** truth links for this exact calibration population; rounding the reported recalls returns integer link counts.

Marginal pool composition:

| Expansion | Added candidates | Added true links | Approx added negatives | True-link fraction of added pool |
|---|---:|---:|---:|---:|
| 80 → 160 | 295,264 | 201 | 295,063 | **0.0681%** |
| 160 → 640 | 1,318,663 | 314 | 1,318,349 | **0.0238%** |
| 80 → 640 | 1,613,927 | 515 | 1,613,412 | **0.0319%** |

The full cap-80 development artifact's 4.216% positive fraction is about **132× larger** than the 0.0319% positive fraction of the marginal 80→640 calibration pool.

Equivalently, the 80→640 expansion introduces roughly **3,133 additional negative candidates for every additional retrieved true link**.

These ratios are not a complaint about retrieval. High-recall retrieval is expected to pay a large negative-candidate cost. The problem is that the classifier is not trained on that marginal distribution before being asked to score it.

### 3. Retrieval widening is valuable, but the matcher captures only part of the available oracle gain

For the final depth-10 model with cap-specific threshold tuning on the same calibration anchors:

| Cap | Macro F0.5 | Blocking oracle | Pair recall | Singleton FP rate |
|---:|---:|---:|---:|---:|
| 80 | 0.924756 | 0.968226 | 0.912150 | 11.51% |
| 160 | 0.927197 | 0.973081 | 0.925308 | 12.30% |
| 640 | 0.930679 | 0.981178 | 0.945863 | 10.32% |

From cap 80→640:

- pair recall improves by **+0.033713**
- oracle macro F0.5 improves by **+0.012952**
- actual macro F0.5 improves by **+0.005923**

So widening is clearly useful, but a large portion of the newly available oracle headroom remains unrealized.

This does **not** prove the training mismatch is the sole cause. Some recovered positives may be intrinsically difficult to classify, and threshold/model capacity also matter. It does show that the current training protocol never gives CatBoost supervised exposure to the enormous lower-ranked negative population it later scores.

### 4. A same-model diagnostic shows increasing singleton FP pressure as cap widens

`reports/wide_calibration.json` evaluates the original cap-80-trained `address_baseline/mixed.cbm` while holding threshold **0.625** fixed across raw retrieval caps.

Its singleton false-positive rate rises monotonically:

- cap 80: **9.92%**
- cap 160: **10.32%**
- cap 320: **10.71%**
- cap 640: **11.11%**

At the same time, macro F0.5 rises because recovered positives outweigh those extra false merges.

This is exactly the expected signature of widening a candidate pool without retraining on the new hard-negative tail: more recall, but increasing precision pressure. The final depth-10/cap-specific threshold sweep partially compensates, so this is diagnostic evidence rather than a causal proof.

## Interpretation

The current pipeline improved retrieval first and matcher training second only in model capacity (depth 8/10), not in **negative distribution**.

The selected depth-10 model is therefore solving a harder inference problem than its labeled fit set represents:

- training sees top-80 retrieval candidates;
- deployment may see top-160 or top-640;
- the extra pool is >99.9% negative;
- many of those negatives are lower-ranked lexical collisions specifically selected because they share blocker evidence with the anchor.

Random negatives would be a weak fix. The useful experiment is to expose training to **retrieved wide-pool hard negatives** while keeping the evaluation candidate pool and anchor split unchanged.

## Smallest high-value empirical follow-up

Do not immediately materialize all cap-640 fit rows and hope RAM forgives us for our sins.

A staged M006 experiment should compare, on identical anchors/features:

1. **Baseline:** current depth-10 model trained on cap-80 fit/early candidates.
2. **Cap-160 matched training:** regenerate fit/early candidates at cap 160 and train the same depth-10 configuration; evaluate on cap-160 calibration.
3. **Hard-negative augmentation:** generate a wider cap-640 fit/early pool, score with the current model, and append a bounded number of highest-scoring false candidates from ranks >80 per anchor to the cap-80 training set; always retain all retrieved positives. Evaluate on cap-640 calibration.

Report at minimum:

- official macro F0.5;
- singleton FP rate overall and India;
- pair recall / oracle (must stay identical for matcher-only comparisons);
- calibration threshold;
- candidate cap;
- number of training rows and positive rate;
- rank distribution of mined negatives;
- wall time / memory.

A gain should be replicated before a fresh integration holdout is consumed.

## Risks

- The 4.216% cap-80 positive fraction is for the full 30,000-anchor artifact, not fit anchors alone. It is used only to characterize the source artifact's class mix.
- Marginal true-link counts are reconstructed from the exact calibration truth count and committed pair recalls; they are aggregate diagnostics, not row-level data.
- The calibration fold has already been used for extensive selection. Tiny gains from the follow-up must be treated skeptically.
- No claim is made that hard-negative retraining will close the full oracle gap.
- France remains unlabeled; wide-negative training should avoid country-specific shortcuts and retain language-agnostic evidence.

## Recommendation

**FOLLOW-UP with high priority.**

The training/deployment mismatch is real in code, the marginal wide pool is extremely negative-heavy, and the current model has never been trained on it. A matched cap-160 retrain is the cheapest decisive test; bounded high-score rank>80 negative mining is the next test if full wide training is too expensive.

Do not alter the selected submission or claim a score gain until those experiments are run on the same calibration anchors and survive red-team checks.
