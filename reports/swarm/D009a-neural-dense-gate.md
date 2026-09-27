# D009a — calibration-selected dense-only penalty for neural32

**Issue:** #293  
**Branch:** `agent/d/D009a-neural-dense-gate`  
**Base:** PR #268 head `fdff7866c4419f4fb645aa8d45a2a15696b8b729`  
**Recommendation:** **REPLICATE**

## Question

INT006 has two provenance classes inside the same cap-32 candidate set. Lexical/character pairs use CatBoost plus cross-encoder logits; dense-only pairs use the cross-encoder plus a provenance prior. The committed evaluation already contains a `dense_gate_sweep`. This task checks the calibration-selected gate, its holdout transfer, and whether the current V5/V6 artifacts include it.

## Protocol

No new challenge rows, model inference, candidate generation, confirmation, or leaderboard feedback were used. The source is the committed `reports/capped_match_evaluation.json` from PR #268, covering the same 4,389 calibration and 3,051 development-holdout anchors.

INT006 V5 uses dense prior **-2.0** and global threshold **0.95**. The existing code chooses `dense_gate_selected` by maximizing **calibration** macro F0.5 only. The selected extra penalty is **+0.5 logit** on dense-only pairs, exactly equivalent to dense prior **-2.5** at the unchanged threshold.

Candidate membership, cap, pair recall, and blocking oracle do not change.

## Result

| Split / slice | V5 | Dense gate | Delta |
|---|---:|---:|---:|
| Calibration all | 0.9772376 | **0.9778440** | **+0.0006064** |
| Calibration India | 0.9760228 | **0.9773927** | **+0.0013699** |
| Calibration US | 0.9780462 | **0.9781444** | **+0.0000982** |
| Holdout all | 0.9707021 | **0.9714487** | **+0.0007466** |
| Holdout India | 0.9683597 | **0.9686828** | **+0.0003232** |
| Holdout US | 0.9722459 | **0.9732715** | **+0.0010256** |

Singleton false-positive rate also improves overall: calibration **1.587% → 1.190%** and holdout **6.030% → 5.025%**. Calibration India is **2.0% → 1.0%**; holdout US is **3.922% → 1.961%**. Holdout India is unchanged at 8.247%.

## Provenance concentration

Under the original V5 rule, dense-only links are only about **3.8%** of selected pairs but account for most selected false positives.

- Calibration: 551 dense-only selections vs 13,891 lexical; dense-only contributes 50/79 false positives (**63.29%**). Selected-pair FP rate is **9.07%** dense-only vs **0.209%** lexical, a **43.47×** ratio.
- Holdout: 378 dense-only selections vs 9,536 lexical; dense-only contributes 43/73 false positives (**58.90%**). Selected-pair FP rate is **11.38%** dense-only vs **0.315%** lexical, a **36.16×** ratio.

This is descriptive selected-edge evidence, not an independent calibration estimate.

## Fragility check

The effect direction is credible, but the exact optimum is not stable enough for immediate promotion.

| Extra dense penalty | Calibration delta | Holdout delta |
|---:|---:|---:|
| -1.0 | -0.001820 | -0.000943 |
| 0.0 | 0 | 0 |
| **+0.5** | **+0.000606** | **+0.000747** |
| +1.0 | +0.000213 | +0.001643 |
| +1.5 | +0.000534 | +0.001597 |
| +2.0 | -0.000088 | +0.001908 |
| +3.0 | -0.000853 | +0.000062 |

The calibration selector correctly chooses **+0.5**. The holdout would prefer +2.0, but holdout information must not be used to retune. The calibration gap between +0.5 and +1.5 is only about **0.000073**, so the magnitude is fragile even though additional dense-only conservatism transfers in the same general direction.

## Production audit

The validated V5 test artifact was generated with threshold **0.95** and dense prior **-2.0**. Its matching SHA-256 is `5a4aff5fcc37c74769ff3db1ebf2d35f85ab2258d80e5425e90ae616f1d7b33d`.

INT007/V6 then reads that exact V5 matching and candidate file, so neither current artifact contains the calibration-selected dense gate.

The production scorer already accepts `dense_prior`; no model change is needed. This branch only isolates a safe rerun namespace and default:

- Modal app: `team517-d009a-dense-gate`
- output: `submission_d009a_dense_gate`
- default dense prior: **-2.5**

Thus a replication cannot overwrite the frozen V5/V6 outputs.

## Executed validation

- Parsed the committed INT006 JSON and recomputed the selector, deltas, candidate/oracle parity, and provenance concentration.
- Focused helper tests: **5/5 PASS**.
- Helper `py_compile`: **PASS**.
- Tests fail closed on candidate-recall drift, oracle drift, or a stored selected gate that is not the calibration argmax.
- The first synthetic test run exposed a shared-object bug in the test fixture; the fixture was corrected and all five tests then passed.

## INT007 interaction

Do not add D009a's holdout delta to INT007's reported gain arithmetically. INT007 was evaluated on the original V5 decisions, and the dense gate can remove links before blank-address recovery. The combined rule needs a direct cached-score evaluation on the same candidate set.

## Compliance

No external identity data, test labels, France labels, leaderboard tuning, record-ID predictive features, candidate additions, or new confirmation use. The holdout is evaluation-only for this task.

## Recommendation

**REPLICATE.** The signal is directionally consistent and improves singleton precision, but the overall holdout gain is below 0.001 and the exact penalty optimum shifts across development splits.

Before any full-test rerun, evaluate INT007 blank-address recovery on top of the fixed calibration-selected **-2.5** dense prior using the existing cached cap-32 scores/candidates; report paired anchor deltas and uncertainty; and do not retune the penalty on holdout.
