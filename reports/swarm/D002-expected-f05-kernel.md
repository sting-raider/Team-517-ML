# D002 — Exact expected-F0.5 prefix decoder kernel

**Issue:** #30  
**Branch:** \`agent/d/D002-expected-f05-kernel\`  
**Baseline reference:** selected cap-640 matcher, confirmation macro F0.5 0.928835  
**Recommendation:** FOLLOW-UP

## Hypothesis

A single global pair threshold ignores the actual competition objective: each source-one anchor is scored as a set, including the empty set, and false positives are expensive. If candidate match probabilities are calibrated, choosing the set that maximizes expected per-anchor F0.5 can make a different decision from thresholding.

This task isolates the decision-theoretic kernel before any full-data integration.

## Change

Added \`src/ber/decision.py\` with an exact small-candidate decoder under explicit assumptions:

- candidate labels are independent Bernoulli variables with supplied probabilities;
- the modeled candidates contain the complete truth set;
- for each possible prediction size, the optimal set is the highest-probability prefix;
- expected row F0.5 is computed exactly using prefix/suffix Poisson-binomial count distributions;
- the empty-set utility is exactly the probability that every modeled candidate is false;
- ties keep the smaller prediction set;
- the exact implementation refuses more than 64 candidates by default rather than silently truncating.

Added \`tests/test_decision.py\` with exhaustive truth-enumeration comparisons and edge cases.

No production inference path, model, threshold, blocker, or selected submission was changed.

## Why probability-ranked prefixes are sufficient under the assumptions

For a fixed prediction size k, compare a set that predicts lower-probability candidate j but not higher-probability candidate i with the swapped set.

Condition on all other labels. The only outcome states that change the numerator are:

- i=true, j=false, where the swap gains one true positive;
- i=false, j=true, where the swap loses one true positive.

Both states have the same total truth cardinality, so they have the same F0.5 denominator. Their probability difference is:

\`\`\`text
p_i (1 - p_j) - (1 - p_i) p_j = p_i - p_j >= 0
\`\`\`

Therefore the swap cannot reduce expected utility. Repeating this exchange proves that the top-k probability prefix is optimal for each fixed k. Searching k=0..n therefore gives the exact optimum under independence and candidate completeness.

## Exact expectation

For a non-empty prefix of size k, let:

- T = number of true labels inside the predicted prefix;
- F = number of true labels outside it.

Then the official row score is:

\`\`\`text
1.25 T / (k + 0.25 (T + F))
\`\`\`

The prefix and suffix candidate groups are independent under the model assumptions. The implementation computes the Poisson-binomial distribution of T and F and sums this score over their joint count distribution.

For k=0, utility is:

\`\`\`text
P(|truth| = 0) = product_i (1 - p_i)
\`\`\`

The implementation is intentionally bounded because evaluating all prefixes is cubic in candidate count in the current exact form. At n <= 64 this is suitable as an offline reference kernel and integration oracle, not as a decoder over all 640 raw candidates for 1.7M anchors.

## Protocol

Tier-1 synthetic verification only.

1. Independently implemented exhaustive enumeration over every binary truth assignment for small candidate sets.
2. Compared every prefix utility from the dynamic-programming formulation to brute-force expectation.
3. Checked empty-set, certain-positive, mixed-cardinality, stable-order, invalid-probability, and explicit-size-bound cases.
4. Independently evaluated the common shortcut that substitutes expected counts into the F0.5 ratio.
5. Swept all 165 sorted probability triples drawn from {0.1, 0.2, ..., 0.9} to look for decision disagreements between the exact expectation and that shortcut.

The current ChatGPT Python/container backend returned a session-level \`ClientError\`, so the committed Python unit test file could not be executed in this chat. The same mathematical kernel and exhaustive enumeration were executed independently in the available deterministic JavaScript runtime. No passing Python-test claim is fabricated.

Reproduction command when a Python worker is available:

\`\`\`bash
PYTHONPATH=src python -m unittest tests.test_decision -v
\`\`\`

## Results

### Exactness sanity checks

The dynamic-programming utilities exactly matched brute-force enumeration in the independently executed cases below (floating-point precision shown):

| Probabilities | Expected utilities for k=0..n | Exact choice |
|---|---|---:|
| [0.6] | [0.400000, 0.600000] | 1 |
| [1.0, 0.0] | [0.000000, 1.000000, 0.555556] | 1 |
| [0.6, 0.4] | [0.240000, 0.560000, 0.528889] | 1 |
| [0.9, 0.55, 0.3] | [0.031500, 0.779571, 0.729389, 0.623610] | 1 |
| [0.51, 0.49, 0.49] | [0.127449, 0.432531, 0.503040, 0.533769] | 3 |

### Ratio-of-expectations is not expected F0.5

A tempting cheap approximation is:

\`\`\`text
1.25 E[TP] / (k + 0.25 E[|truth|])
\`\`\`

This is not the expectation of the ratio and can change the action.

For probabilities **[0.4, 0.3, 0.1]**:

- exact empty-set utility = **0.378000**
- exact k=1 utility = **0.373905**
- exact decision = **predict empty**
- shortcut k=1 value = **0.416667**
- shortcut decision = **predict one**

For probabilities **[0.5, 0.4, 0.1]**:

- exact k=1 = **0.459286**
- exact k=2 = **0.473182**
- exact decision = **predict two**
- shortcut gives 0.500000 for both k=1 and k=2; a precision-favoring tie-break would choose the wrong k=1 action.

Across the deterministic 165-case sorted-triple grid, the shortcut selected a different prefix size in **8 / 165 = 4.85%** of cases. This grid is a synthetic sanity check, not an estimate of disagreement on challenge data.

## Error analysis / integration risks

The exact mathematics does **not** make the current candidate probabilities suitable inputs automatically.

### 1. Candidate completeness is false today

Current confirmation pair recall at cap 640 is about **0.947246**, with blocking-oracle macro F0.5 about **0.980951**. Therefore some true links live outside the candidate set.

The kernel's empty-set probability \`product(1-p)\` is optimistic when there is nonzero probability of a missed true link. Deploying it unchanged could encourage false singleton predictions. Empirical integration must either:

- model probability mass for missed matches / true cardinality outside the decoded subset, or
- treat this exact candidate-complete decoder as a controlled heuristic and judge only end-to-end held-out macro F0.5.

### 2. Candidate labels are correlated

Multiple S2/S3 records can describe the same S1 business. Their match events are not guaranteed independent. Independence can make both cardinality and empty-set probabilities overconfident.

A later D002 integration should compare:
- raw calibrated pair probabilities,
- provenance/cardinality-conditioned calibration,
- a singleton probability or missed-match prior,
- and the exact independence decoder as a reference.

### 3. Current CatBoost scores are not guaranteed calibrated probabilities

The selected model was tuned for ranking/threshold performance, not probability calibration. Feeding uncalibrated scores into expected utility can be worse than the global threshold even if the decoder is mathematically exact.

### 4. Runtime

The reference implementation stores prefix/suffix count distributions and evaluates all prefix utilities exactly. It is appropriate for small postfiltered sets and offline validation. It is not an acceptable direct 640-candidate x 1.7M-anchor production decoder.

## Baseline comparison

No competition metric changed in this task.

- Current reference confirmation macro F0.5: **0.928835**
- New macro F0.5: **not measured**
- Delta: **not claimed**

A valid empirical D002 follow-up must use the exact same anchors/candidates/scores for the global-threshold and expected-utility decisions, fit any calibration only on the designated calibration data, and evaluate the decision rule on a separate holdout. Candidate recall must be reported unchanged.

## Risks

- Independence and candidate-completeness assumptions are material, not decorative footnotes.
- Probability calibration can leak if fitted/evaluated on the same anchors.
- A prefilter before the bounded exact decoder changes the modeled truth space and must be explicit.
- Reusing the repeatedly inspected confirmation set to tune this decoder would invalidate its role as confirmation.
- Tiny gains require paired entity bootstrap or replication.

## Recommendation

**FOLLOW-UP.**

Keep the exact kernel as a reference implementation and reject the ratio-of-expectations shortcut as an “exact expected F0.5” decoder.

The next empirical D002 task should wait for reusable current per-anchor probability/candidate artifacts, then:

1. calibrate probabilities out-of-fold or on calibration only;
2. restrict exact decoding to a small explicit top-N while accounting for tail/missed-match mass;
3. compare against the existing 0.625 global threshold on identical anchors;
4. report macro F0.5, singleton FPR, non-singleton recall/cardinality slices, India/US slices, unchanged candidate recall, and paired uncertainty.

No selected submission change is justified by this kernel-only task.
