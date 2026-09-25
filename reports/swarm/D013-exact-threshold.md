# D013 — Exact probability-threshold optimization vs coarse 0.025 grid

**Issue:** #135  
**Branch:** `agent/d/D013-exact-threshold`  
**Baseline:** main `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`  
**Recommendation:** **FOLLOW-UP / REPLICATE ON PRIVATE CALIBRATION ARTIFACT**

## Hypothesis

The selected matcher and candidate-budget studies choose a global probability threshold with `experiment.choose_threshold`. In the operating region below 0.96, that function searches a fixed grid with **0.025 spacing**.

For a fixed candidate set and fixed model probabilities, the official per-anchor macro F0.5 changes only when the threshold crosses an observed probability. Therefore an exact sweep over observed probability breakpoints contains every prediction set reachable by the coarse grid and can weakly dominate its calibration score.

The open question is not whether the exact optimizer can beat or tie the grid mathematically. It can. The useful competition question is whether the improvement on the real 4,389-anchor calibration slice is large and stable enough to survive selection variance.

## Change

Added opt-in analysis code:

- `src/ber/thresholds.py::choose_threshold_exact`

and synthetic regression tests:

- `tests/test_exact_threshold.py`

No caller is changed. The current coarse-grid `experiment.choose_threshold` remains the production/default path.

## Current behavior audited

`src/ber/experiment.py::choose_threshold` searches:

```python
np.unique(np.r_[
    np.arange(.05, .96, .025),
    .97, .98, .99, .995, .999
])
```

and selects the maximum `(macro_f0_5, threshold)`, so exact score ties prefer the higher threshold.

The same helper is used by:

- baseline model calibration in `experiment.py`;
- selected depth-8/depth-10 wide-model calibration in `tune.py`;
- cap-specific threshold selection in `candidate_budget.py`;
- historical wide/lexical calibration in `wide_evaluate.py`.

The selected depth-10 artifact is recorded at threshold **0.625**. Candidate-budget results use only **0.575** or **0.625** across the recorded caps, which is consistent with the coarse grid but is not evidence that either value is the exact optimum.

## Exact optimizer semantics

`choose_threshold_exact` preserves the current decision semantics:

- prediction rule is `prob >= threshold`;
- candidate misses remain in the truth-size denominator;
- singleton truth + empty prediction scores 1;
- macro averaging is per selected Source-1 anchor;
- equal probability values enter together;
- score ties prefer the higher threshold.

It sorts selected candidate rows by probability once, starts from the highest achievable threshold state, then incrementally updates only the affected anchor as probability breakpoints are crossed.

Every distinct prediction set reachable by a threshold in `[0,1]` is evaluated exactly once.

## Deterministic proof of weak dominance

Let `S(t)` be the prediction set produced by threshold `t`.

Between two adjacent observed probability values, `S(t)` is constant. At an observed value `p`, the production rule `>=` adds all rows whose probability equals `p`.

Therefore every prediction set produced by any coarse-grid threshold is also represented either:

- by one observed-probability breakpoint in the exact sweep; or
- by threshold 1.0 for the all-empty state when no selected probability equals 1.

The exact search optimizes over a superset of the coarse grid's distinct prediction states. On the **same anchors, candidates, probabilities, and metric**, its calibration macro F0.5 cannot be lower except for implementation/numerical error.

That is an algorithmic guarantee, not a generalization guarantee.

## Synthetic result

A deliberately minimal case demonstrates why 0.025 resolution can matter:

One anchor has:

| Candidate | Label | Probability |
|---|---|---:|
| A | true | 0.613 |
| B | false | 0.612 |

At exact threshold **0.613**:

- prediction = {A}
- row F0.5 = **1.000000**

The current grid cannot choose 0.613.

At grid threshold 0.625:

- prediction = empty
- row F0.5 = **0**

At grid threshold 0.600:

- prediction = {A, B}
- row F0.5 = **0.555556**

So the coarse-grid optimum is **0.555556 at 0.600**, while the exact optimum is **1.000000 at 0.613**.

This toy gap is intentionally extreme and must not be interpreted as an expected competition delta. It proves only that the discretization can exclude the optimal reachable set.

## Existing real-artifact context

The committed baseline calibration curve around its selected region is:

| Threshold | Calibration macro F0.5 |
|---:|---:|
| 0.600 | 0.921028 |
| **0.625** | **0.921486** |
| 0.650 | 0.921133 |

The neighboring-grid gaps are only about 0.00035–0.00046. That shape leaves room for an interior optimum, but the committed curve cannot identify it.

The selected depth-10 candidate-budget artifact similarly reports thresholds only at grid values:

- caps 20–160: **0.575**
- caps 240–640: **0.625**

No exact depth-10 score is claimed because the private `depth10_wide_probabilities.npy` and candidate metadata are not committed and are not accessible through this runtime.

## Tests authored

The focused tests cover:

1. a breakpoint optimum missed by the coarse grid;
2. exact score weakly dominating the grid on a mixed multi-anchor case;
3. equal probability values entering together;
4. missing truth candidates remaining in the denominator;
5. singleton empty-set behavior and higher-threshold tie-breaking;
6. no-candidate evaluation;
7. nonfinite/out-of-range probability rejection.

Intended command:

```bash
PYTHONPATH=src python -m unittest tests/test_exact_threshold.py -v
```

The current chat's Python/container process service returns `ClientError`, so these Python tests were not executed locally. The key breakpoint example was independently recomputed in the available JavaScript execution runtime:

- exact threshold 0.613 -> **1.000000**
- grid best 0.600 -> **0.555556**
- threshold 0.625 -> **0**

This limitation is recorded rather than disguised as a passing test run.

## Overfitting risk

An exact search evaluates far more candidate states than the ~42-point fixed grid. On a 4,389-anchor calibration slice, that increases threshold-selection flexibility.

Therefore a tiny exact calibration gain is **not automatically an improvement**.

A trustworthy promotion protocol should:

1. run exact and coarse selection on the identical calibration candidates/probabilities;
2. record exact threshold, calibration delta, and number of evaluated states;
3. use paired anchor-level bootstrap/error-diff tooling to measure whether the changed decisions are broad or concentrated;
4. check threshold stability under calibration resampling or predefined subfolds;
5. only after a material, stable result, evaluate once on an untouched integration/confirmation gate according to the project's freeze policy.

Do not repeatedly tune the exact method against the same confirmation set.

## Complexity

For N selected candidate rows:

- sorting: `O(N log N)`;
- sweep: `O(N)`;
- memory: `O(N + number_of_anchors)`.

This is more expensive than evaluating a small fixed grid, but threshold selection is an offline calibration step and is tiny relative to model training / wide candidate materialization.

If the private wide pool is ~1.9M rows on 4,389 calibration anchors, the implementation should be runtime-profiled before integration. No runtime claim is made here because Python execution was unavailable.

## Red-team checks

- **Metric semantics:** designed to mirror current `choose_threshold`; I017 independently confirmed the repository's F0.5 semantics.
- **Candidate recall/oracle:** unchanged; D013 changes only the selected probability threshold.
- **Model probabilities:** unchanged.
- **Training:** unchanged.
- **Label leakage:** no new leakage channel; threshold selection uses the same calibration labels already used by the grid.
- **Confirmation/frozen holdout:** not consumed.
- **Leaderboard feedback:** not used.
- **Tiny-gain skepticism:** required; exact calibration dominance can be pure selection variance.
- **Production behavior:** unchanged by this branch unless a future caller explicitly opts into the new helper.

## Recommendation

**FOLLOW-UP / REPLICATE.**

The coarse threshold grid is strictly unnecessary from an optimization perspective and can provably miss the best reachable prediction set. The exact optimizer is worth evaluating because it is cheap relative to retraining and leaves retrieval/model outputs unchanged.

Do **not** promote it based on synthetic dominance. Recover the private selected depth-10 wide probability artifact and run exact-vs-grid on the same 4,389 calibration anchors first. Report:

- coarse threshold / macro F0.5;
- exact threshold / macro F0.5;
- delta;
- singleton FP overall and India;
- US/India macro F0.5;
- number of anchors whose predicted set changes;
- paired bootstrap interval / error-set diff;
- threshold stability under calibration resampling;
- runtime.

A sub-0.001 gain should be presumed fragile until replicated.

## Reproduction

```bash
PYTHONPATH=src python -m unittest tests/test_exact_threshold.py -v
```

The implementation is opt-in; current production threshold selection remains untouched.
