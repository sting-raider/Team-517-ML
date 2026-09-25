# R021 — Candidate-budget Pareto audit under organizer size criterion

**Issue:** #96  
**Branch:** `agent/r/R021-candidate-budget-pareto`  
**Main baseline inspected:** `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`  
**Recommendation:** **FOLLOW-UP**

## Hypothesis

The committed same-slice cap studies already contain enough evidence to identify candidate-budget configurations that are dominated on matcher quality versus candidate-set size, and to quantify how quickly marginal quality gains decay as candidate pools widen. This matters because the organizer guidance recorded in `RULES_INSIGHTS.md` explicitly says smaller candidate sets per Source-1 entity are favored in final review alongside matching quality.

The experiment does **not** assume that a smaller cap is automatically better, and it does not infer an undisclosed organizer weighting between score and candidate size.

## Change

Added a deterministic aggregate-only audit helper:

```text
tools/experiments/r021_candidate_budget_pareto.py
```

and focused regression tests:

```text
tests/test_r021_candidate_budget_pareto.py
```

The helper reads only committed aggregate reports. It does not read challenge rows, generate candidates, score new pairs, or consume confirmation/frozen holdouts.

Before comparing model utility with retrieval statistics, it fails loudly unless the candidate metrics in `reports/wide_calibration.json` exactly agree with `reports/retrieval_study.json` for every shared configuration.

## Protocol

Inputs on the same 4,389-anchor calibration set:

- `reports/wide_calibration.json`
- `reports/retrieval_study.json`
- `reports/tuning.json`
- `reports/data_audit.json`

The cap sweep in `wide_calibration.json` uses the historical `address_baseline/mixed.cbm` classifier. For each raw-retrieval and lexical-shortlist configuration it chooses a threshold on the calibration anchors and evaluates the official per-anchor macro F0.5.

The selected depth-10 CatBoost in `reports/tuning.json` is a different model and is recorded only on the full 640-candidate wide pool. Therefore this audit treats the depth-10 640 score as context only and **does not extrapolate it to smaller caps**.

Exact audit command:

```bash
python tools/experiments/r021_candidate_budget_pareto.py --repo-root . --out /tmp/r021.json
```

Focused tests:

```bash
python -m unittest tests/test_r021_candidate_budget_pareto.py -v
```

Local validation in the available Python runtime: **2/2 tests passed**. The aggregate helper run took approximately **0.77 s wall time** and **93,100 KB max RSS**.

No confirmation or frozen evaluation window was consumed.

## Results

### Same-classifier cap sweep

| Configuration | Macro F0.5 | Pair recall | Blocking oracle F0.5 | Singleton FP rate | Candidate p50 | Candidate p90 |
|---|---:|---:|---:|---:|---:|---:|
| raw 80 | 0.921486 | 0.912150 | 0.968226 | 9.9206% | 80 | 80 |
| raw 160 | 0.924181 | 0.925308 | 0.973081 | 10.3175% | 160 | 160 |
| raw 320 | 0.926112 | 0.937156 | 0.977303 | 10.7143% | 320 | 320 |
| raw 640 | 0.927373 | 0.945863 | 0.981178 | 11.1111% | 597 | 640 |
| lexical 80 | 0.926253 | 0.932247 | 0.975645 | 10.7143% | 65 | 70 |
| lexical 160 | 0.926412 | 0.934603 | 0.976311 | 10.7143% | 144 | 148 |
| lexical 320 | 0.926809 | 0.938466 | 0.977698 | 10.7143% | 304 | 306 |
| lexical 640 | 0.927373 | 0.945863 | 0.981178 | 11.1111% | 597 | 640 |

Under the two-dimensional audit objective of **higher macro F0.5 and fewer median candidates**, raw retrieval at caps 80, 160, and 320 is Pareto-dominated by at least one lexical-shortlist configuration. In particular:

- lexical 80 beats raw 160: **0.926253 vs 0.924181** macro F0.5, with p50 **65 vs 160** candidates;
- lexical 80 also narrowly beats raw 320: **0.926253 vs 0.926112**, with p50 **65 vs 320**;
- lexical 160 and lexical 320 remain Pareto-efficient in this measured sweep;
- the 640 configurations converge to the same candidate pool and score.

This dominance statement applies only to the historical classifier/configuration used by `wide_calibration.json`.

### Marginal widening returns

For raw retrieval, macro-F0.5 gains shrink as the pool widens:

| Transition | Δ macro F0.5 | Δ pair recall | Δ oracle F0.5 | Δ singleton FP rate | Added p50 candidates |
|---|---:|---:|---:|---:|---:|
| 80 → 160 | +0.002695 | +0.013158 | +0.004855 | +0.3968 pp | +80 |
| 160 → 320 | +0.001931 | +0.011849 | +0.004222 | +0.3968 pp | +160 |
| 320 → 640 | +0.001261 | +0.008706 | +0.003875 | +0.3968 pp | +277 |

For the lexical shortlist:

| Transition | Δ macro F0.5 | Δ pair recall | Δ oracle F0.5 | Δ singleton FP rate | Added p50 candidates |
|---|---:|---:|---:|---:|---:|
| 80 → 160 | +0.000159 | +0.002357 | +0.000666 | 0.0000 pp | +79 |
| 160 → 320 | +0.000397 | +0.003862 | +0.001386 | 0.0000 pp | +160 |
| 320 → 640 | +0.000564 | +0.007397 | +0.003480 | +0.3968 pp | +293 |

Across the lexical endpoints, cap 80 → 640 yields:

- macro F0.5: **+0.001120**
- pair recall: **+0.013616**
- blocking-oracle macro F0.5: **+0.005533**
- singleton FP rate: **+0.3968 percentage points**, exactly one additional false-positive singleton among 252 calibration singletons
- median candidate count: **65 → 597**, a **9.18×** increase
- observed macro gain per 100 added median candidates: approximately **+0.000211**

The widening improves retrieval/oracle quality more than the historical matcher converts into end-to-end score. The oracle-minus-matcher gap rises from **0.049392** at lexical 80 to **0.053805** at lexical 640. This is consistent with the already-documented wide-negative distribution mismatch, but this audit does not claim causality.

### Test candidate-volume implications

The test set contains **1,732,544 Source-1 anchors**. A simple cap × anchor upper bound gives:

| Cap | Maximum candidate entries |
|---:|---:|
| 80 | 138,603,520 |
| 160 | 277,207,040 |
| 320 | 554,414,080 |
| 640 | 1,108,828,160 |

Using calibration p50 merely as a scale illustration, not an estimate of the exact test mean, lexical 80 corresponds to about **112.6M p50-equivalent entries**, while the 640 pool corresponds to about **1.034B**.

The exact final candidate-file size cannot be inferred from p50; final selection needs the actual test candidate-count mean and distribution.

### Selected model guardrail

The selected depth-10 model at cap 640 scores **0.930679** macro F0.5 on these calibration anchors, above the historical classifier's 0.927373 at the same cap. However, `tuning.json` contains **no depth-10 same-model measurements at caps 80, 160, or 320**.

Therefore R021 does **not** conclude that lexical 80, 160, 320, or 640 is the final optimal budget. The missing same-model cap sweep is the decisive next measurement.

## Error analysis

This audit exposes three concrete failure modes in the current final-cap reasoning:

1. **Cap-only comparison can be misleading.** Raw 160/320 look like natural intermediate budgets, but lexical 80 delivers higher measured macro F0.5 with dramatically fewer candidates under the historical classifier.
2. **Retrieval headroom is not matcher headroom.** Wider pools raise the blocking oracle substantially, while the matcher captures a smaller fraction of that gain and singleton FP rises at the widest pool.
3. **Model mismatch can invalidate a cap recommendation.** The selected depth-10 matcher is stronger than the model used for the cap sweep, and its response to truncation is unmeasured.

The helper also guards against a quieter failure: comparing candidate metrics from mismatched retrieval artifacts. Its provenance/parity assertion fails if the shared candidate statistics disagree.

## Interpretation

The committed evidence is strong enough to reject a simplistic rule of “use cap 640 because it has the highest local score.” Candidate-set size is now an explicit review consideration, and several much smaller lexical pools lie on the measured score/size Pareto frontier.

It is **not** strong enough to select the final cap. The right next experiment is cheap relative to retraining or rebuilding retrieval: score the already-selected depth-10 probabilities on the exact same wide calibration candidate pool after deterministic truncation/shortlisting at the candidate boundary, using the same official metric and candidate-count diagnostics.

If the existing wide depth-10 probabilities and candidate metadata are still available on the private/Modal volume, this should not require a new full S2/S3 retrieval run.

## Risks

- The cap sweep repeatedly used the calibration set, so tiny differences such as +0.000159 should not be treated as robust improvements.
- Thresholds in `wide_calibration.json` were selected separately per configuration on the same calibration anchors. A promoted cap comparison should use a clean protocol appropriate to the selected matcher.
- Median candidate count is not file size. Actual mean/total candidate counts on test must be measured.
- The organizer guidance establishes that smaller candidate sets are favored, but not a numeric tradeoff function. This audit intentionally does not invent one.
- France has no labels, so no measured cap comparison here establishes French retrieval robustness.
- R021 reuses committed aggregate artifacts; it is not an independent full-data reproduction of those artifacts.

## Recommendation

**FOLLOW-UP.**

Do not promote a smaller cap or discard cap 640 from R021 alone. Instead, run a **selected depth-10 same-model candidate-budget sweep** on the existing wide candidate/probability artifact before final blocker selection. Report macro F0.5, pair/entity/all-matches recall, blocking oracle, singleton FP overall/India, country slices, actual candidate mean/p50/p90/p99/max, and total candidate entries on identical anchors.

Until that measurement exists, cap 640 should be treated as the current score-maximizing measured selected-model configuration, **not** as an automatically optimal final submission configuration under the organizer's candidate-size criterion.

## Follow-up tasks

1. Evaluate the selected depth-10 model at lexical/raw 80, 160, 320, and 640 on exactly the same calibration anchors without retraining.
2. If a compact cap is competitive, replicate the tradeoff on a fresh integration gate rather than repeatedly tuning the current calibration block.
3. Measure exact candidate totals/mean on the final test export for every surviving cap; do not substitute p50 for total file size.
4. Combine this result with M006 wide-hard-negative work: a matcher trained on the actual wider negative distribution may change the Pareto frontier.
