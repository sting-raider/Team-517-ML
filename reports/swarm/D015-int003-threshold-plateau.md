# D015 — INT003 threshold plateau and selection robustness

## Hypothesis

INT003's selected threshold of 0.625 may be a brittle grid optimum. If the calibration curve collapses immediately on either side, modest probability drift could erase part of the confirmed gain; if 0.625 sits near the center of a broad near-optimal region, threshold micro-tuning is low-value and the current decision rule is comparatively robust.

## Change

No model, retriever, threshold, candidate pool, or inference behavior was changed.

Added:
- `tools/experiments/d015_threshold_plateau.py`: deterministic calibration-curve plateau audit.
- `tests/test_d015_threshold_plateau.py`: focused tests for contiguous-component semantics, higher-threshold tie-breaking, and invalid grids.

## Protocol

Input is only the committed `reports/int003_depth10.json` calibration curve for the selected INT003 depth-10, 57-feature, cap-160 model.

For absolute epsilon values 0.0005, 0.001, 0.002, and 0.005:

1. identify the discrete calibration optimum using the production higher-threshold tie-break;
2. mark grid points with macro F0.5 at least `best - epsilon`;
3. take the contiguous marked component containing the optimum;
4. report endpoints, width, grid-point count, midpoint, and the selected threshold's offset from midpoint.

The already-published development holdout and frozen 45,001–50,000 confirmation values at the preselected threshold 0.625 are context only. No alternative threshold is evaluated or selected on either held-out slice.

Commands:

```bash
python tools/experiments/d015_threshold_plateau.py --artifact reports/int003_depth10.json
python -m unittest tests/test_d015_threshold_plateau.py -v
```

Local reproduction of the helper logic and focused unit suite: **3/3 tests pass**.

No raw challenge rows, candidate probabilities, new holdout/confirmation windows, France labels, leaderboard feedback, or external identity data are used.

## Results

### Discrete optimum

The committed INT003 calibration curve peaks at:

- threshold: **0.625**
- calibration macro F0.5: **0.9491209588**

Immediate grid neighbors:

| Threshold | Macro F0.5 | Loss vs 0.625 |
|---:|---:|---:|
| 0.600 | 0.9485951033 | 0.0005258555 |
| **0.625** | **0.9491209588** | **0** |
| 0.650 | 0.9485591078 | 0.0005618510 |

Both immediate penalties are about 5.3–5.6e-4 macro F0.5. They are small relative to the confirmed v3-v2 gain of 0.007914, but too large for either neighbor to enter the strict 0.0005 contiguous band.

### Epsilon-optimal components

| Absolute epsilon | Component | Grid points | Width | Midpoint | 0.625 offset |
|---:|---:|---:|---:|---:|---:|
| 0.0005 | [0.625, 0.625] | 1 | 0.000 | 0.625 | 0 |
| 0.0010 | **[0.575, 0.675]** | 5 | 0.100 | **0.625** | **0** |
| 0.0020 | **[0.525, 0.725]** | 9 | 0.200 | **0.625** | **0** |
| 0.0050 | **[0.450, 0.800]** | 15 | 0.350 | **0.625** | **0** |

At the decision-relevant 0.001 and 0.002 tolerances, 0.625 is exactly the midpoint of the contiguous near-optimal component. Even the much looser 0.005 band is centered exactly on the selected threshold.

A small wrinkle worth recording: threshold 0.675 is globally within 0.0005 of the maximum, but the intervening 0.650 point is just outside that tolerance. The preregistered contiguous-component rule therefore correctly leaves the 0.0005 component as the singleton point 0.625 rather than pretending the local curve is perfectly flat.

### Held-out context at the fixed selected threshold

At the already-selected 0.625 threshold:

- calibration macro F0.5: **0.9491209588**
- development holdout: **0.9447832215**, delta **-0.0043377373**
- frozen INT003 confirmation: **0.9501984900**, delta **+0.0010775312**

These are generalization observations at one fixed threshold only. They do not reveal the holdout or confirmation threshold curves and were not used to choose 0.625.

### Comparison with prior INT002 plateau audit

D014 found INT002 threshold 0.65 centered in its 0.001 band [0.625, 0.675] and 0.002 band [0.575, 0.725]. INT003's corresponding components are wider on the lower-threshold side: [0.575, 0.675] and [0.525, 0.725], while remaining centered on the selected value.

This comparison is descriptive only. The models and candidate distributions differ, so it is not a paired score comparison.

## Error analysis

1. **Aggregate calibration grid only.** The artifact does not expose per-candidate probabilities here, so this audit cannot measure an exact observed-probability optimum between grid points.
2. **Grid spacing is 0.025 near the optimum.** A narrower best cutoff may exist between tested thresholds, but the broad plateau means any claimed micro-gain should be treated skeptically until paired on held-out development data.
3. **No paired uncertainty between threshold points.** Neighbor losses around 0.0005 are smaller than many plausible sampling/calibration effects. They are descriptive, not proof that 0.625 is intrinsically superior to every nearby cutoff.
4. **Confirmation remains contamination-safe.** The 45,001–50,000 confirmation window is referenced only at the threshold fixed before confirmation. No alternative threshold was tried on it.
5. **Changed models require recalibration.** This result does not justify hard-coding 0.625 for later retrievers, feature sets, or hard-negative training runs.

## Interpretation

The artifact-level evidence supports retaining INT003's current threshold rather than spending a submission cycle on threshold nibbling.

The key geometry is not merely that 0.625 wins one coarse grid point. It is centered exactly in broad 0.001, 0.002, and 0.005 contiguous near-optimal regions. That makes the selected decision rule comparatively insensitive to modest probability-scale drift around the optimum.

The remaining INT003 confirmation error is far larger than the local threshold differences, so the next high-value work remains retrieval recall, ambiguity/singleton handling, and matcher quality rather than post-hoc threshold micro-optimization.

## Risks

- Epsilon bands are descriptive tolerances, not confidence intervals.
- The committed artifact must correspond to the selected INT003 model; its recorded depth 10, 57 features, cap 160, and threshold 0.625 match the promoted report.
- The result says nothing about France accuracy because France has no labels.
- A materially changed matcher or candidate pool must recalibrate from its own development probabilities.

## Recommendation

**PROMOTE / RETAIN the current INT003 threshold of 0.625.**

Do not spend a frozen or confirmation window trying to harvest a few ten-thousandths from the threshold. Exact calibration-only optimization is reasonable inside the next genuine retraining cycle, but the current selected threshold is already centered in a broad near-optimal plateau.
