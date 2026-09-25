# Submission 2: INT002 matched-pool CatBoost

Decision: **PROMOTE** the frozen depth-10 matcher, threshold 0.65, cap160.
The full test export is running; no public score is available for this file yet.

| Same 5,000 confirmation anchors | Submitted-v1 model | INT002 |
|---|---:|---:|
| Macro F0.5 | 0.927580 | 0.940478 |
| India | 0.895932 | 0.913639 |
| US | 0.948294 | 0.958045 |
| Singleton false-positive rate | 8.364% | 5.818% |

Paired macro gain: **0.012899**, entity-bootstrap 95% interval
[0.010188, 0.015616]
(2,000 resamples, seed517). 505 anchors improve and 182 regress. The interval
covers this sample's variation, not French transfer or hidden-leaderboard risk.
Candidate pair recall and oracle are unchanged: 0.927799 and 0.974176.

## Method and evidence

Train on 108,115 anchors / 15,431,847 cap160 candidate pairs, without positive
injection. Use the original 47 text/comparison features plus four unlabeled
inventory-frequency features, score-only dense candidate rank, and relative
retrieval score. CatBoost depth10, 1,798 retained trees, learning rate0.05,
l2_leaf_reg10, per-anchor weighting, seed517. A Modal L4 fits the model in
352 seconds; training plus evaluation/reporting takes374.93 seconds.

Depth10 was chosen on development evidence from INT001. That experiment's
ordinal-rank feature indirectly used ID tie order, so its checkpoints were
rejected. INT002 rebuilt features in a fresh cache using dense rank over score
only. The fixed synthetic SQL check confirms equal-score candidates receive
equal model-facing rank. Original47 features remain the exact prefix.

Threshold0.65 is chosen only on the existing4,389 calibration anchors:
macro0.943003 vs baseline0.927197. Reused development holdout:0.938129 vs0.926837.
The confirmation sample comprises positions40,001–45,000 under the established
md5 sample ordering. These anchors were excluded from fitting and selection.
Full-S1 research audits have inspected labels globally; this is a matcher
confirmation, not a claim that no research process has ever accessed the rows.
Do not reuse this window to tune the next model.

India singleton false positives increase by one on the development holdout
(14 vs13) but decrease by one on confirmation (14 vs15); overall India score
improves in both. I020's holdout singleton-composition warning is relevant.
France has no labels, and this confirmation does not establish its accuracy.

Model SHA256: `c93d00e616553ccba727377979873aee88e499fc34a74a28106de41783646950`.
Private model: `team517-business-er/project/experiments/int002/depth10/mixed.cbm`.
No datasets, PDFs, model binaries, or predictions are committed to Git.

## Reproduction

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
modal run -d modal_v2.py --action train --depth 10
modal run -d modal_v2.py --action confirm --depth 10
modal run -d modal_v2.py --action score --depth 10
```

See MODAL.md for staging and download commands. Cached features live under
int002; use new directories for any changed feature/data/blocker configuration.

The independent retrieval experiment raises the measured cap160 oracle to
0.981086 but is not enabled here. It needs a matcher trained on its candidate
pool. See COORDINATOR_PLAN.md for research triage and next priorities.
