# D016 — INT003 singleton false-positive stability and score headroom

## Hypothesis

INT003 improved overall and India macro F0.5, but its truth-empty (singleton) false-positive rate varies across evaluated slices. D016 asks whether singleton precision is stable enough to justify a dedicated decision layer, and how much official macro F0.5 a perfect singleton-only correction could recover.

## Dependency correction

**A first D016 checkpoint compared INT003 with the historical `baseline_v2_fused_pool` diagnostic. That comparison is withdrawn.**

I028 / PR #211 subsequently found that `baseline_v2_fused_pool` was not a feature-contract-pure frozen-v2 counterfactual: it reused v3's changed `relative_retrieval_score` normalization on sub-unit fused RRF scores. Therefore the published v2-on-fused score and singleton counts cannot isolate matched-pool retraining.

D016 no longer uses that diagnostic for any conclusion. The following results are unaffected because they depend only on the actual INT003 path and its blocker oracle:

- INT003 singleton counts and rates;
- Wilson intervals and cross-slice descriptive stability;
- exact perfect-singleton-fix macro headroom;
- I027's current-v3 actual-vs-oracle error budget.

The earlier same-fused-pool retraining attribution, pooled v2-fused comparison, and derived non-singleton component are superseded and must not be cited.

## Exact change

Added a deterministic committed-artifact audit, `tools/experiments/d016_int003_singleton_stability.py`, plus focused tests. The helper reads only:

- `reports/int003_depth10.json`
- `reports/int003_depth10_confirmation.json`

It reconstructs exact INT003 singleton FP counts from published rates, reports Wilson 95% intervals, pools the existing INT003 slices descriptively, and computes the exact macro-F0.5 ceiling of a perfect singleton-only fix.

No production matcher, threshold, candidate pool, or export behavior changes.

## Protocol

Existing INT003 evaluated slices only:

- calibration: 4,389 anchors, reused development/model-selection slice;
- development holdout: 3,051 anchors, reused development slice;
- frozen INT003 confirmation: 5,000 anchors at sample517 positions 45,001–50,000.

No new challenge rows, labels, candidate probabilities, threshold tuning, France labels/pseudo-labels, leaderboard feedback, or fresh holdout were consumed. Calibration and development holdout are **not** independent confirmation; pooled rates are descriptive only.

Reproduction:

```bash
python tools/experiments/d016_int003_singleton_stability.py \
  --train-report reports/int003_depth10.json \
  --confirmation reports/int003_depth10_confirmation.json \
  --out reports/swarm/D016-int003-singleton-stability.json

python -m unittest tests/test_d016_int003_singleton_stability.py -v
```

Focused validation: **4/4 tests PASS**.

## Current baseline context

INT003 frozen confirmation:

- macro F0.5: **0.95019849**
- India: **0.93269861**
- US: **0.96208054**
- blocker oracle: **0.98091686**
- within-candidate matcher/decision gap: **0.03071837**

I027 showed that 61.68% of the remaining confirmation deficit is inside the retrieved candidate pool. D016 bounds how much of that gap could possibly be recovered by correcting truth-empty false positives alone.

## Results

### INT003 singleton FPR is not numerically stable across slices

| Slice | Overall | India | US |
|---|---:|---:|---:|
| calibration | 16/252 = **6.35%** | 8/100 = **8.00%** | 8/152 = **5.26%** |
| dev holdout | 21/199 = **10.55%** | 15/97 = **15.46%** | 6/102 = **5.88%** |
| frozen confirmation | 13/262 = **4.96%** | 8/114 = **7.02%** | 5/148 = **3.38%** |

Frozen-confirmation Wilson 95% intervals are wide:

- overall: **2.92%–8.30%**
- India: **3.60%–13.24%**
- US: **1.45%–7.66%**

Across the three existing slices, the observed rate range is **5.59 pp overall**, **8.45 pp India**, and **2.50 pp US**. The 7.02% India confirmation value should not be treated as a precise operating constant.

Descriptive pooling of the three disjoint evaluated INT003 slices gives 50/713 = **7.01%** overall, 31/311 = **9.97%** India, and 19/402 = **4.73%** US. Because calibration and development holdout are reused model-development data, these are not deployment estimates.

### Full-pipeline v2→v3 singleton behavior is mixed, not a clean retraining attribution

On the frozen confirmation using each model's native candidate and feature path, the published v2 original-pool singleton FPR is 12/262 = **4.58%** versus INT003 13/262 = **4.96%** overall. India moves 6/114 = **5.26%** to 8/114 = **7.02%**, while US improves 6/148 = **4.05%** to 5/148 = **3.38%**.

This valid end-to-end comparison changes retrieval, model, and feature semantics together. It shows no uniform country-independent singleton regression and cannot identify which component caused the India change.

### A perfect singleton-only fix has a bounded ceiling

On the frozen confirmation, eliminating every INT003 singleton false positive with zero collateral damage would recover at most:

| Slice | perfect-fix macro headroom | share of total deficit | share of within-candidate gap |
|---|---:|---:|---:|
| all | **+0.002600** | 5.22% | **8.46%** |
| India | **+0.003956** | 5.88% | **10.34%** |
| US | **+0.001679** | 4.43% | **6.56%** |

This is the key planning result. Singleton precision matters, especially for India, but even an impossible oracle correction cannot close most of INT003's 0.030718 within-candidate gap.

## Error analysis / red-team

- Exact FP counts are recoverable because each published FPR multiplied by its singleton count is an integer; the helper fails if that parity is violated.
- Calibration and development holdout are reused development data and are included only for descriptive stability.
- I028's comparison-contract finding was discovered after D016's initial checkpoint. D016 explicitly withdraws every conclusion that depended on `baseline_v2_fused_pool`.
- No corrected v2-on-fused singleton counts are invented. They require rerunning the already-consumed diagnostic on the private Modal artifacts after the I028 compatibility patch.
- D001/D011/D012 found little or no useful Source-1-only signal for singleton/source-presence prediction. Any future empty-set gate should use candidate-level probabilities, score gaps, provenance, cross-source evidence, or learned cardinality evidence rather than another Source-1-only prior.

## Recommendation

**FOLLOW-UP**, with bounded priority.

Keep INT003 and threshold **0.625**. D015 already shows the global threshold lies in a broad near-optimal plateau. A candidate-evidence empty-set gate remains worth testing, especially for India, but its frozen-confirmation ceiling is only **+0.002600 macro overall** and **+0.003956 India** even with perfect classification and zero collateral damage.

Prioritize broader matcher/set-decision work that can attack the remaining 0.030718 within-candidate gap. When private candidate probabilities are available, evaluate top probability, top-vs-second margin, retrieval provenance, and predicted cardinality on development calibration/holdout. Do not consume a new frozen window merely to repair the historical v2-on-fused diagnostic.
