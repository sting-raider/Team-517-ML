# D016 — INT003 singleton false-positive stability and score headroom

## Hypothesis

INT003 improved overall and India macro F0.5, but its truth-empty (singleton) false-positive rate is visibly higher on some development slices. The question is whether this is a stable precision defect worth a dedicated decision layer, or mostly slice noise with too little score headroom to justify priority over the much larger general matcher/decision gap identified by I027.

## Exact change

Added a deterministic committed-artifact audit, `tools/experiments/d016_int003_singleton_stability.py`, plus focused tests. The helper reads only:

- `reports/int003_depth10.json`
- `reports/int003_depth10_confirmation.json`

It reconstructs exact singleton FP counts from the published rates, reports Wilson 95% intervals, pools the three existing slices descriptively, compares INT003 against the frozen v2 matcher on the **same fused candidate pool**, and computes the exact macro-F0.5 ceiling of a perfect singleton-only fix.

No production matcher, threshold, candidate pool, or export behavior changes.

## Protocol

Existing evaluated slices only:

- calibration: 4,389 anchors, reused development/model-selection slice;
- development holdout: 3,051 anchors, reused development slice;
- frozen INT003 confirmation: 5,000 anchors at sample517 positions 45,001–50,000.

No new challenge rows, labels, candidate probabilities, threshold tuning, France labels/pseudo-labels, leaderboard feedback, or fresh holdout were consumed. Calibration and development holdout are **not** treated as independent confirmation. Their pooled rate is descriptive evidence only.

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

I027 showed that 61.68% of the remaining confirmation deficit is now inside the retrieved candidate pool. D016 asks how much of that can plausibly be assigned to truth-empty false positives.

## Results

### 1. The absolute singleton FPR is not stable across slices

INT003 truth-empty false positives:

| Slice | Overall | India | US |
|---|---:|---:|---:|
| calibration | 16/252 = **6.35%** | 8/100 = **8.00%** | 8/152 = **5.26%** |
| dev holdout | 21/199 = **10.55%** | 15/97 = **15.46%** | 6/102 = **5.88%** |
| frozen confirmation | 13/262 = **4.96%** | 8/114 = **7.02%** | 5/148 = **3.38%** |

Frozen-confirmation Wilson 95% intervals are wide:

- overall: **2.92%–8.30%**
- India: **3.60%–13.24%**
- US: **1.45%–7.66%**

So the exact 7.02% India confirmation rate should not be treated as a precise operating constant. Across the three existing slices, the rate range is 5.59 pp overall, 8.45 pp India, and 2.50 pp US.

### 2. The direction versus the frozen v2 matcher on the same fused pool is consistent

Although the absolute rate moves by slice, INT003 has **more singleton false positives than the frozen v2 matcher on the same fused candidate pool in every measured split and country slice**.

Overall extra INT003 FPs versus v2-on-fused-pool:

- calibration: **+7**
- dev holdout: **+11**
- confirmation: **+8**

India: **+4 / +7 / +7**. US: **+3 / +4 / +1**.

Descriptive pooling across the three disjoint evaluated slices gives:

| Slice family | v2 on fused pool | INT003 | delta |
|---|---:|---:|---:|
| overall | 24/713 = 3.37% | 50/713 = **7.01%** | **+3.65 pp** |
| India | 13/311 = 4.18% | 31/311 = **9.97%** | **+5.79 pp** |
| US | 11/402 = 2.74% | 19/402 = **4.73%** | **+1.99 pp** |

These pooled values are not an independent generalization estimate. They do show a repeated directional tradeoff from matched-pool retraining, strongest in India.

### 3. Matched-pool retraining gains substantially more elsewhere than it loses on singletons

Because a truth-empty anchor scores 1 only when the prediction is empty and 0 otherwise, the count difference gives its exact macro contribution. On the same fused pool:

| Slice | INT003 macro gain vs frozen v2 | singleton component | non-singleton net component |
|---|---:|---:|---:|
| calibration | +0.016727 | **-0.001595** | +0.018322 |
| dev holdout | +0.016318 | **-0.003605** | +0.019923 |
| confirmation | +0.019326 | **-0.001600** | +0.020926 |

India confirmation is even clearer: matched-pool retraining gains **+0.034351** macro overall on the same candidate pool while seven extra singleton FPs cost **-0.003462**. The non-singleton net component is therefore +0.037813.

This is not an argument to revert retraining. It is evidence for a **targeted precision correction**, if an inference-safe signal can identify risky empty-truth cases without sacrificing the much larger non-singleton gain.

### 4. A perfect singleton-only fix has a bounded ceiling

On the frozen confirmation, eliminating every INT003 singleton false positive with zero collateral damage would recover at most:

| Slice | perfect-fix macro headroom | share of total deficit | share of within-candidate gap |
|---|---:|---:|---:|
| all | **+0.002600** | 5.22% | **8.46%** |
| India | **+0.003956** | 5.88% | **10.34%** |
| US | **+0.001679** | 4.43% | **6.56%** |

This is worth something, especially for India, but it cannot close most of INT003's matcher/decision deficit. The larger prize remains ambiguity, false merges, and false negatives among non-singleton anchors.

## Error analysis / red-team

- Exact FP counts are recoverable because each published FPR multiplied by its singleton count is an integer; the helper fails if this parity is violated.
- The calibration and development-holdout slices were used during prior model development. They are included only to test directional stability, not as fresh confirmation.
- The v2 comparison is specifically the frozen v2 matcher applied to the **same v3 fused pool**, so candidate membership is controlled. It is not the original v2 production pipeline comparison.
- No paired singleton identities are committed, so D016 does **not** report a McNemar/pairwise significance test between v2 and v3. Count direction is descriptive.
- The pooled Wilson intervals treat the concatenated evaluated anchors as a binomial summary; because two slices are reused development data, this is not a deployment confidence interval.
- D001/D011/D012 found little or no useful Source-1-only signal for singleton/source-presence prediction. A useful correction therefore needs candidate-level probabilities, score gaps, provenance, cross-source evidence, or a learned set/cardinality signal rather than another Source-1-only prior.

## Recommendation

**FOLLOW-UP**, with bounded priority.

Do **not** revert INT003 matched-pool retraining and do not globally raise the 0.625 threshold just to suppress singleton FPs. D015 already shows 0.625 sits in a broad overall plateau, and the singleton penalty is much smaller than the non-singleton gain from retraining.

A targeted candidate-evidence singleton/empty-set gate is justified as a decision-layer experiment because the precision defect repeats across all three measured slices and is strongest in India. However, its frozen-confirmation ceiling is only +0.002600 macro overall even under a perfect oracle-like correction. Prioritize it behind or alongside broader matcher/set-decision work that can attack the remaining 0.030718 within-candidate gap.

The next executable experiment, when candidate probabilities are available, should evaluate an inference-safe empty-set score using top probability, top-vs-second margin, retrieval provenance, and predicted cardinality. Tune only on existing development calibration, verify on the reused development holdout, and reserve any new frozen window until a materially distinct model is ready.
