# D018 — cardinality-conditioned F0.5 error costs and hard-cap ceilings

## Hypothesis

INT003's remaining confirmation deficit is now dominated by within-candidate matcher/decision loss rather than singleton-only error. Before testing cardinality-aware decoders, quantify the exact official macro-F0.5 cost of false positives versus false negatives as true match cardinality changes, and determine whether simple global output-size caps would impose an unacceptable score ceiling even under perfect candidate ranking.

## Exact change

This experiment does not change retrieval, features, CatBoost, thresholds, or submission inference.

It adds a deterministic full-population audit helper that expresses the repository's official row metric using only truth size, true positives, and false positives; scans complete Source-1 plus ground truth; and reports:

- the truth-cardinality population,
- one-FP and one-FN losses around a perfect set,
- the share of anchors where one extra false positive costs more than omitting one true match,
- optimistic perfect-ranking macro-F0.5 ceilings for global hard prediction caps 1 through 10,
- US and India slices.

The helper fails loud on duplicate or misaligned Source-1/truth anchor IDs.

## Protocol

Data: complete supplied training population, no sampling.

- train_source1.tsv: 2,206,821 anchors; SHA256 591af0e1dfeb65cab71ea6ee8cb69df00f92d6ba6fa79e05746c938775d14973
- train_ground_truth.tsv: 2,206,821 anchors; SHA256 70bc1d8a16c667e0155c2105d0ab2ebe41d7e7a85d8a529e3ca81c6c3a5af037
- Countries: US and India only, exactly as supplied.
- No Source-2/Source-3 text was needed.
- No candidate probabilities, model outputs, confirmation/frozen holdouts, France pseudo-labels, leaderboard feedback, or external entity data were used.
- Record IDs are only join keys for Source-1 country attribution, never predictive evidence.

Exact execution:

    python tools/experiments/d018_cardinality_cost_surface.py \
      --source1 /mnt/data/train_source1.tsv \
      --truth /mnt/data/train_ground_truth.tsv \
      --out /mnt/data/d018.json

Focused validation:

    python -m unittest tests.test_d018_cardinality_cost_surface -v

Measured full scan: 12.69 s wall time, 630,696 KiB peak RSS (about 616 MiB). Focused tests: 6/6 PASS.

## Metric parity and baseline

The audit uses the same formula as src/ber/metrics.py::row_score:

F0.5 = 1.25 * TP / (0.25 * |truth| + |prediction|),

with an empty-truth/empty-prediction singleton score of 1.

The correct same-population baseline for this mathematical ceiling experiment is the unconstrained perfect prediction, macro F0.5 = 1.0. The hard-cap numbers below are losses from that exact same full labeled population. They are not direct re-scores of INT003 and must not be compared as paired model deltas.

As a parity check, the scan reproduces the established full-population facts: 123,247 singleton anchors (5.584821%) and mean truth cardinality 3.461253.

## Results

Truth cardinality is not small enough for an aggressive global match cap:

| Global hard output cap | Perfect-ranking macro F0.5 ceiling | Loss from 1.0 | Anchors with truth size above cap |
|---:|---:|---:|---:|
| 1 | 0.696388 | 0.303612 | 1,964,417 |
| 2 | 0.872821 | 0.127179 | 1,589,205 |
| 3 | 0.947828 | 0.052172 | 1,058,364 |
| 4 | 0.980628 | 0.019372 | 574,249 |
| 5 | 0.993766 | 0.006234 | 252,292 |
| 6 | 0.998332 | 0.001668 | 87,424 |
| 7 | 0.999641 | 0.000359 | 23,456 |

A global cap of 5 therefore cannot reach the team's aspirational 0.998 even with perfect ranking and zero false positives. Cap 6 is the smallest tested cap whose labeled-population ceiling exceeds 0.998, and it does so narrowly at 0.998332. This is a ceiling/guardrail, not evidence that cap 6 is optimal for the real model.

US and India behave almost identically. Cap-5 ceilings are 0.993779 US and 0.993747 India; cap-6 ceilings are 0.998330 US and 0.998335 India. The conclusion is therefore not driven by one labeled country.

The local F0.5 asymmetry also changes sharply with cardinality:

| True matches | Loss from +1 false positive | Loss from -1 true match | FP/FN loss ratio |
|---:|---:|---:|---:|
| 0 | 1.000000 | n/a | n/a |
| 1 | 0.444444 | 1.000000 | 0.444x |
| 2 | 0.285714 | 0.166667 | 1.714x |
| 3 | 0.210526 | 0.090909 | 2.316x |
| 4 | 0.166667 | 0.062500 | 2.667x |
| 5 | 0.137931 | 0.047619 | 2.897x |
| 6 | 0.117647 | 0.038462 | 3.059x |

For cardinality 1, recall dominates: dropping the sole true link is worse than adding one false link. Starting at cardinality 2, the metric becomes increasingly precision-heavy. Exactly 1,964,417 anchors, 89.0157% of the full labeled population and 94.2811% of non-singletons, lie in the regime where one additional false positive costs more than one omitted true match.

Descriptively, adding one false positive to a perfect set loses 0.248457 macro points on average over all anchors, while dropping one true match loses 0.136581 on average over non-singletons. Those averages have different eligible populations and should not be treated as a direct policy ratio.

## Error analysis

This result explains why one global cardinality heuristic is structurally awkward:

- true singletons require extreme precision because any false positive changes their row score from 1 to 0;
- cardinality-1 non-singletons require recall because one false negative also changes their row score from 1 to 0;
- the large cardinality-2+ majority is precision-heavy under F0.5;
- nevertheless, hard truncation sacrifices too many true links once the cap falls below roughly 6 on the labeled population.

The observed truth distribution is median 3, p90 6, p95 6, p99 8, maximum 11. A decoder therefore needs anchor-specific evidence about whether to emit zero, one, or several links rather than a universal small set-size limit.

## Red-team checks

- The formula was checked directly against latest-main src/ber/metrics.py.
- 6/6 focused tests pass, including singleton behavior, known set-count cases, monotonic hard-cap ceilings, small-file end-to-end audit, and fail-loud duplicate handling.
- The complete scan reproduces prior D006a population counts and cardinality aggregates.
- Source-1 and truth have exactly 2,206,821 unique aligned anchors in this run.
- No holdout, confirmation, or model probability artifact was inspected, so this cannot leak threshold-selection information.
- No France conclusion is drawn; France has no supplied labels and its cardinality distribution could differ.

## Risks and limits

These are optimistic ceilings under perfect candidate ranking and no false positives below the chosen cap. They do not estimate the score of an actual top-K decoder, which could be much lower if rank/calibration is imperfect.

The 0.998 guardrail is based on the supplied labeled US/India population. It is not a guarantee for the hidden test mixture or France.

This experiment does not identify which anchors should receive larger or smaller sets. Source-1-only singleton/cardinality priors have already tested near-random, so the next useful signal must come from candidate probabilities, margins, provenance, cross-source evidence, or an equivalent inference-time observable.

## Recommendation

**FOLLOW-UP / adopt as a decision-design guardrail.**

Do not deploy a universal hard output cap of 5 or lower if the 0.998 aspiration remains relevant. Do not interpret "F0.5 is precision-heavy" as permission to truncate every anchor to a tiny set.

The next empirical decision experiment should use out-of-fold candidate probabilities to choose anchor-specific set sizes, with D002 expected-F0.5 decoding or another calibrated cardinality-aware rule, and must compare against INT003 on the same candidate pool and calibration anchors. A cap may still be used as a safety maximum, but 6 is only a mathematical minimum for the labeled-population 0.998 ceiling, not a recommended operating point.
