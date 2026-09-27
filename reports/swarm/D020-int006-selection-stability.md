# D020 — INT006 calibration-to-holdout decision-grid stability

## Hypothesis

INT006 selected its dense-only prior and final probability threshold on the 4,389-anchor calibration split, then evaluated the fixed choice on a separate 3,051-anchor development holdout. Because these local splits have been used repeatedly, the selection itself needs a bounded stability audit: does the calibration ordering transfer, or is `dense_prior_-2` merely a sharp calibration peak?

## Protocol

Aggregate-only audit of the complete directly comparable five-variant decision grid already committed in PR #268 at `reports/capped_match_evaluation.json`.

No challenge rows, pair probabilities, model inference, new thresholds, confirmation/frozen windows, France labels, or leaderboard feedback were consumed. This audit does **not** retune on holdout.

Metrics:
- calibration and holdout macro F0.5 ranks;
- Spearman/Kendall rank agreement;
- selected-point regret to the post-hoc holdout-best grid point;
- India/US holdout regret;
- calibration→holdout score drop;
- singleton false-positive transfer.

Three focused ranking tests pass.

## Results

| Variant | Prior | Threshold | Calibration F0.5 | Cal rank | Holdout F0.5 | Hold rank | Cal→holdout drop |
|---|---:|---:|---:|---:|---:|---:|---:|
| dense_prior_-2 | -2 | 0.95 | **0.977238** | **1** | 0.970702 | 2 | 0.006535 |
| dense_prior_-1 | -1 | 0.875 | 0.975721 | 2 | **0.971204** | **1** | 0.004517 |
| dense_prior_0 | 0 | 0.95 | 0.974135 | 3 | 0.968458 | 3 | 0.005677 |
| dense_prior_1 | 1 | 0.97 | 0.972420 | 4 | 0.967623 | 4 | 0.004797 |
| cross_only | — | 0.95 | 0.968358 | 5 | 0.963088 | 5 | 0.005269 |

Calibration→holdout rank agreement is **Spearman 0.90 / Kendall 0.80**. There is only **one discordant pair out of ten**, the swap between priors -2 and -1.

The selected -2 point is only **0.000502 macro F0.5** behind the post-hoc holdout-best -1 point. That is far below the scale at which this repeatedly used holdout should justify retuning.

### Country transfer

The top-pair swap is a country tradeoff, not a general collapse:

- **India holdout:** selected -2 is the best grid point at **0.968360**. Its regret is exactly 0.
- **US holdout:** -1 is best at 0.974146; selected -2 is 0.972246, regret **0.001900**.
- On calibration, -2 also wins India, while -1 is slightly better in US. The direction of that country tradeoff therefore transfers.

### Singleton precision

The selected -2 point has calibration singleton FPR **1.587%** and holdout **6.030%**. The holdout-best -1 point has **3.571%** and **8.040%**, respectively. So the tiny +0.000502 post-hoc holdout macro advantage of -1 comes with worse singleton false-positive behavior on both splits.

### Caution

The selected -2 point has the largest calibration→holdout macro drop in this five-point grid, **0.006535**. That is a mild optimism signal and another reason not to treat local 0.97x scores as independent confirmation. It does not overturn the ranking result: -2 remains holdout rank 2, India-best, and singleton-safer.

## Red-team checks

- All five rows use the same cap-32 candidate pool and anchor sets in the committed artifact.
- The holdout is used only for diagnosis here, never to choose a replacement production prior/threshold.
- No new labels or candidate probabilities were loaded.
- No France accuracy claim is possible.
- No leaderboard feedback influenced this audit.

## Recommendation

**PROMOTE-STABILITY, not a new model promotion.**

Keep the calibration-selected `dense_prior_-2` / threshold 0.95 decision for INT006/V5. Do **not** switch production to -1 based on the 0.000502 post-hoc holdout edge. The grid ordering transfers strongly, the only inversion is tiny, and -2 preserves the better India and singleton-FP behavior.

Future decision work should target new evidence/features rather than squeezing this already-stable five-point prior grid.

## Reproduction

```bash
python tools/experiments/d020_int006_selection_stability.py \
  --input reports/capped_match_evaluation.json \
  --out reports/swarm/D020-int006-selection-stability.json

python -m unittest tests/test_d020_int006_selection_stability.py -v
```
