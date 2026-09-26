# INT004: address token alignment on the INT003 matcher

**Decision: REJECT.** The M004 one-to-one fuzzy address-token alignment added five
features to the selected INT003 model without changing its candidate pool or cap160.
It did not improve the independent development holdout, so no fresh confirmation
window or test export was consumed.

The experiment used the same 108,115 fit anchors and 16,043,969 fit pairs as
INT003. CatBoost depth10 trained 1,800 trees. The 57-feature frozen INT003 model
was scored on the *same* candidate pool using the first 57 columns of the 62-feature
INT004 matrix, so the baseline comparison preserves feature meaning and retrieval.
The v4 threshold 0.65 was selected on calibration; v3 retained 0.625.

| Split | Entities | Frozen INT003 | INT004 | Delta |
|---|---:|---:|---:|---:|
| Calibration | 4,389 | 0.949121 | 0.949726 | +0.000605 |
| Development holdout | 3,051 | 0.944783 | 0.943727 | -0.001056 |
| India holdout | 1,212 | 0.917541 | 0.915804 | -0.001737 |
| US holdout | 1,839 | 0.962737 | 0.962130 | -0.000607 |

The blocker oracle is unchanged at 0.980461 on calibration and 0.979300 on
holdout. Training ran on Modal L4 using the private prepared challenge database;
no external entity evidence or pretrained model was used. The full aggregate
receipt is `reports/int004_depth10.json`. Model binaries, feature matrices, and
record-level data remain on the private Modal Volume.

This result argues against promoting fuzzy token alignment by itself. The current
matcher is close enough to this feature family that more of the same has low
expected value. The measured blocker deficit is a stronger next target.
