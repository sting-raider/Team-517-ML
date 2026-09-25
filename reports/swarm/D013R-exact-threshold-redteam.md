# D013R — Red-team exact probability-threshold optimizer

**Issue:** #166  
**Target:** D013 / PR #141, head `0f5c49bab58d4a188ea912670e09ed795f36ca0d`  
**Branch:** `agent/i/D013R-exact-threshold-redteam` (stacked on D013)  
**Recommendation:** PROMOTE as an opt-in analysis utility; REPLICATE on the real calibration artifact before selected-pipeline adoption

## Question

Does `ber.thresholds.choose_threshold_exact` actually enumerate every reachable prediction state under the intended threshold semantics and return the same official per-anchor macro F0.5 optimum as an exhaustive reference?

## Static audit

The implementation was checked against the production `experiment.choose_threshold` semantics:

- predictions use `prob >= threshold`;
- candidate misses remain in the truth denominator;
- empty-truth + empty-prediction rows score 1;
- equal-probability candidates enter together;
- macro averaging is over the selected anchor IDs;
- score ties prefer the higher threshold.

No challenge probability artifact or labels were required.

## Boundary clarification

D013 operates on **probability cutoffs in [0, 1]**.

This matters only at the exact boundary `max(prob) == 1.0`: threshold 1.0 still includes those rows, so the empty prediction set is not reachable within the allowed cutoff domain.

The stacked branch documents that domain explicitly and adds a regression test for it. No scoring behavior was changed.

## Executed tests

The seven original D013 tests plus two red-team boundary/validation tests were executed locally:

```bash
PYTHONPATH=/tmp/d013r python -m unittest discover -s /tmp/d013r/tests -v
```

Result: **9 / 9 passed**.

Covered cases include:

- a breakpoint missed by the 0.025 coarse grid;
- exact weak dominance over the coarse grid on a mixed case;
- duplicate probability values;
- candidate misses;
- singleton/empty-set tie behavior;
- zero candidate rows;
- p=1.0 boundary semantics;
- duplicate/out-of-range anchor indices;
- non-finite/out-of-range probabilities.

## Independent exhaustive validation

A separate brute-force reference enumerated every reachable threshold state and recomputed predictions from scratch.

Protocol:

- deterministic RNG seed 517;
- 20,000 randomized cases;
- 1–5 anchors;
- random truth cardinalities including missing positives;
- 0–6 candidate rows per anchor;
- discrete probabilities including 0.0 and 1.0 plus duplicated intermediate values;
- random non-empty anchor-index subsets.

Result:

- best macro F0.5 matched within 1e-12 in **20,000 / 20,000** cases;
- selected threshold, including the higher-threshold tie-break, matched exactly in **20,000 / 20,000** cases.

## Row-order stability

To stress incremental floating-point updates and equal-probability grouping:

- 2,000 randomized four-anchor cases;
- 20 candidate rows each;
- four duplicated probability levels;
- each case permuted 10 times.

Result: selected threshold and score were stable across all **20,000** permutations checked.

## Runtime feasibility

Synthetic stress:

- 500,000 candidate rows;
- 5,000 anchors;
- continuous probabilities, therefore about 500,001 evaluated states;
- deterministic ~1% positive candidate pattern plus some candidate-miss truth.

Observed local runtime:

- **1.690 s**
- **295,808 candidate rows/s**
- peak process RSS: **128,792 KiB**

This is a local synthetic throughput measurement, not a production or challenge-runtime guarantee, but it shows the exact sweep is operationally plausible rather than a quadratic state enumeration.

## Result

### Correctness

**PASS.**

No algorithmic mismatch was found. The implementation's incremental sweep agrees with exhaustive threshold-state evaluation on all tested cases and preserves the intended higher-threshold tie-break.

### Coarse-grid relation

The exact sweep evaluates all distinct observed probability breakpoints plus the reachable empty state when `max(prob) < 1`. Every prediction set induced by the current coarse grid has an equivalent observed-probability state, so the exact optimizer weakly dominates the coarse grid on identical rows under the documented [0,1] threshold domain.

### Competition metric

**Not measured.**

The selected depth-10 calibration probability array is private/uncommitted in this runtime, so no official macro-F0.5 delta is claimed. The committed coarse-grid context around the selected operating region remains:

- threshold 0.600: macro F0.5 0.921028
- threshold 0.625: macro F0.5 0.921486
- threshold 0.650: macro F0.5 0.921133

Those values are context only and were not reused for tuning here.

## Risks

- **Empirical gain unknown:** mathematical weak dominance does not imply a material score increase.
- **Calibration overfitting:** exact breakpoint search has more degrees of freedom than a coarse grid; a tiny development gain may be less stable out of sample.
- **Threshold stability:** a selected threshold sitting on one candidate probability can move under model seed/data perturbations.
- **Duplicate candidate rows:** the current pipeline is expected to provide unique anchor-target candidates; this red-team did not broaden D013 into a candidate-integrity validator.
- **No confirmation use:** this is deliberate. Confirmation/frozen windows should not be spent deciding whether a mathematically exact calibration search works.

## Recommendation

**PROMOTE** the opt-in exact-threshold utility and its tests as a correct analysis primitive. It does not alter production/default threshold selection by itself.

For selected-pipeline adoption, **REPLICATE / FOLLOW-UP** on the identical 4,389-anchor depth-10 calibration artifact:

1. coarse and exact thresholds on the same probability rows;
2. paired anchor-level diff;
3. paired bootstrap/sign test if the gain is small;
4. threshold/score stability under at least a permitted seed or development-slice perturbation;
5. no confirmation/frozen holdout until the development evidence is convincing.

A sub-0.001 calibration gain should not be promoted on one breakpoint search alone.
