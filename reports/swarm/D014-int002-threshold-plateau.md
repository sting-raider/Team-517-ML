# D014 — INT002 threshold plateau and selection robustness

## Hypothesis
INT002's selected threshold of 0.65 may be a brittle single-grid optimum. If nearby thresholds are materially worse, small probability-calibration drift could erase part of the model gain; if 0.65 is the center of a broad near-optimal region, the current threshold is a reasonable robust choice and further threshold micro-tuning should be treated skeptically.

## Change
No model, threshold, retrieval, calibration, or inference behavior was changed.

Added:
- `tools/audit_threshold_plateau.py`: deterministic parser for a committed calibration curve; reports the discrete optimum, immediate-neighbor losses, and the contiguous epsilon-optimal component containing the optimum.
- `tests/test_threshold_plateau.py`: three focused tests for component/midpoint semantics, neighbor losses, and invalid threshold ordering.

Implementation commits:
- helper: `cda8217023ac258233a98b81b63c1107048ed55c`
- tests: `5ffe68e01d46452b8f7c69c5dc47afd41c620ea8`

## Protocol
Input is only the committed `reports/int002_depth10.json` calibration curve from current main. It contains the 4,389-anchor calibration result used to select the INT002 threshold.

Primary metric: official per-entity macro F0.5 already stored in the artifact.

For absolute epsilon values 0.0005, 0.001, 0.002, and 0.005:
1. identify the discrete best threshold;
2. mark grid points with macro F0.5 >= best - epsilon;
3. take the contiguous marked component containing the best threshold;
4. report its endpoints, width, grid-point count, midpoint, and the selected threshold's offset from that midpoint.

The already-published INT002 holdout and 40,001:45,000 confirmation score at threshold 0.65 are used only as context. No alternative threshold is evaluated or selected on those slices.

Command:

```bash
python tools/audit_threshold_plateau.py \
  --artifact reports/int002_depth10.json
python -m unittest tests/test_threshold_plateau.py -v
```

3/3 focused tests pass. The test body completes below the timer's 1 ms display resolution in this runtime.

No raw challenge rows, candidate probabilities, new confirmation window, frozen holdout, leaderboard feedback, or external data are used.

## Results

### Discrete optimum
The committed calibration curve peaks at:

- threshold: **0.65**
- calibration macro F0.5: **0.9430028381**

Immediate grid neighbors:

| Threshold | Macro F0.5 | Loss vs 0.65 |
|---:|---:|---:|
| 0.625 | 0.9421576166 | 0.0008452215 |
| **0.650** | **0.9430028381** | **0** |
| 0.675 | 0.9424051256 | 0.0005977124 |

The local peak is not perfectly flat at the 0.0005 level, but the neighboring penalties are below 0.001 macro F0.5.

### Epsilon-optimal components

| Absolute epsilon | Component | Grid points | Width | Midpoint | 0.65 offset from midpoint |
|---:|---:|---:|---:|---:|---:|
| 0.0005 | [0.650, 0.650] | 1 | 0.000 | 0.6500 | 0 |
| 0.0010 | **[0.625, 0.675]** | 3 | 0.050 | **0.6500** | **0** |
| 0.0020 | **[0.575, 0.725]** | 7 | 0.150 | **0.6500** | **~0** |
| 0.0050 | [0.500, 0.825] | 14 | 0.325 | 0.6625 | -0.0125 |

For the tighter and more decision-relevant 0.001 and 0.002 tolerances, the selected 0.65 threshold is exactly the midpoint of the near-optimal component. A simple robustness-oriented midpoint rule therefore chooses the **same threshold**.

At 0.60 the loss is 0.0014580168; at 0.70 it is 0.0013007057. Thus the curve degrades gradually over a substantial neighborhood rather than collapsing immediately away from 0.65.

### Same selected threshold on held-out slices
At the already-selected 0.65 threshold:

- calibration: 0.9430028381
- development holdout: 0.9381292957, delta from calibration **-0.0048735424**
- untouched INT002 confirmation: 0.9404781799, delta from calibration **-0.0025246582**

These are generalization observations at one fixed threshold, **not** evidence about the shape of holdout/confirmation threshold curves. D014 does not use either held-out slice to retune 0.65.

## Error analysis
1. **Aggregate curve only.** The committed artifact does not contain the per-candidate probabilities needed to run D013's exact observed-probability optimizer here.
2. **Grid spacing is 0.025 near the optimum.** The true best reachable probability cutoff may lie between grid values. D014 cannot quantify the exact optimizer's gain from aggregate curve points.
3. **No paired uncertainty between thresholds.** A 0.0006–0.00085 neighbor difference is small enough that it should not be treated as statistically decisive without per-anchor paired outputs.
4. **Holdout/confirmation provide one threshold each.** Their good transfer at 0.65 supports the selected model generally but cannot prove that 0.65 is their own optimum.
5. **Confirmation remains untouched for selection.** No conclusion here depends on choosing a threshold after looking at confirmation performance.

## Interpretation
The evidence does **not** support changing INT002's 0.65 threshold.

Although 0.65 is the unique grid point within 0.0005 of the calibration maximum, it sits exactly at the center of both the 0.001 and 0.002 near-optimal bands. That is the desirable geometry for a threshold chosen under sampling/calibration uncertainty: modest drift in either direction incurs gradual rather than catastrophic loss.

D013's exact threshold optimizer remains mathematically valid and may find a slightly better calibration cutoff from the underlying probabilities. But the expected value of chasing a tiny calibration-only increment is limited unless the exact gain is clearly larger than the local curve noise and survives the normal development holdout protocol. It must not be tuned on the consumed confirmation window.

## Risks
- The analysis assumes the committed calibration curve belongs to the exact selected INT002 model/config; the artifact records depth 10, cap 160, 53 features, and threshold 0.65 consistently.
- The epsilon values are descriptive tolerances, not statistical confidence intervals.
- A future retrained model, changed candidate distribution, or recalibration can have a different optimum; 0.65 should not be hard-coded as a universal threshold.
- The confirmation composition audit I023 is active separately; D014 does not pre-empt its conclusions about the representativeness of that 5,000-anchor slice.

## Recommendation
**PROMOTE / RETAIN the current INT002 threshold of 0.65.**

There is no artifact-level case for moving it. For future materially changed models or candidate pools, use D013's exact calibration-only optimizer and then evaluate the fixed selected threshold on held-out data. Do not spend a confirmation window searching for another few ten-thousandths of calibration macro F0.5.

## Follow-up tasks
No separate threshold-tweak experiment is warranted for the current frozen INT002 model. Exact optimization belongs inside the next genuine matcher/retrieval retraining cycle, not as post-hoc confirmation tuning.
