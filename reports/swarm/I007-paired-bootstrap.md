# I007 — Paired entity-bootstrap utility for tiny metric deltas

## Hypothesis
A deterministic paired bootstrap over Source-1 entities gives the swarm a more relevant uncertainty estimate for experiment deltas than comparing two independently bootstrapped system confidence intervals. Because competing systems are evaluated on the same anchors, the bootstrap should resample the per-anchor candidate-minus-baseline difference.

## Change
Added `src/ber/bootstrap.py` with:
- paired entity-level percentile bootstrap over already-computed per-anchor row scores;
- exact anchor-universe equality checks;
- finite / [0,1] row-score validation;
- duplicate-anchor checks, including collisions after string normalization;
- observed macro-score delta, percentile interval, bootstrap standard error, and bootstrap fraction with delta > 0;
- deterministic seed and configurable replicate count/confidence;
- optional categorical slice comparisons with fail-loud slice-label agreement;
- TSV/CSV CLI input and JSON output;
- method and NumPy-version provenance in every result.

Added `tests/test_bootstrap.py` with eight focused synthetic regression tests.

## Protocol
Tier 0/1 statistical/infrastructure validation only. No challenge holdout, confirmation window, raw entity data, model predictions, or leaderboard feedback was consumed.

Test command:

```bash
PYTHONPATH=/mnt/data/i007/src python -m unittest discover -s /mnt/data/i007/tests -v
```

Execution environment:
- Python 3.13.5
- NumPy 2.3.5 in this ChatGPT runtime (the repository pins NumPy 2.3.2)
- seed 517 where a fixed seed was required

A CLI smoke test used four synthetic anchors split across India/US with an exact +0.05 candidate shift:

```bash
PYTHONPATH=/mnt/data/i007/src python -m ber.bootstrap base.tsv cand.tsv \
  --slice-col country --replicates 1000 --seed 517
```

## Baseline
The current `src/ber/confirm.py` computes a bootstrap confidence interval for one system by resampling that system's per-anchor scores. That is useful for a single-score interval, but it does not itself provide a paired interval for the difference between two systems evaluated on the same anchors.

There was no reusable paired-delta utility on `main` at task start.

## Results
Focused suite: **8/8 tests passed**.

Measured local test command resource use:
- wall time: 0.64 s
- peak RSS: 94,256 KiB

The tests verify:
- identical systems produce observed delta 0, interval [0,0], and zero bootstrap SE;
- a constant +0.05 per-anchor shift produces an exact +0.05 paired bootstrap interval, demonstrating that pairing is preserved;
- fixed seed produces deterministic output;
- anchor-universe mismatch fails loudly;
- duplicate table anchors fail loudly;
- anchors that collide after string normalization fail loudly;
- non-finite and out-of-range row scores fail loudly;
- per-slice deltas are computed only when slice labels agree exactly.

The CLI smoke test returned:
- baseline mean: 0.50
- candidate mean: 0.55
- observed delta: +0.05
- 95% percentile interval: approximately [0.05, 0.05]
- bootstrap fraction(delta > 0): 1.0
- India delta: +0.05
- US delta: +0.05

No competition F0.5 improvement is claimed; this task changes experiment comparison tooling only.

## Error analysis
The most important failure mode is comparing different anchor universes. The CLI rejects this rather than silently intersecting them. This protects against the particularly seductive mistake of reporting a tiny gain whose two inputs were not evaluated on identical entities.

The implementation also rejects malformed score artifacts before resampling. Slice comparison rejects country/category drift between the two inputs.

The first local test run exposed a bad synthetic fixture that generated a negative row score. The implementation rejected it as designed; the fixture was corrected to remain within [0,1].

## Interpretation
For same-anchor experiment comparisons, resampling per-anchor deltas preserves covariance between the two systems. This is the statistical object the swarm actually cares about when deciding whether a small observed macro-F0.5 change is robust on that evaluation set.

The constant-shift test is a useful adversarial check: a paired bootstrap must retain the exact shift in every resample. Independent resampling of the two systems would introduce artificial variation even when every anchor improved by exactly the same amount.

## Risks
- Bootstrap intervals describe sampling variation over the evaluated anchor population; they do not protect against repeated holdout tuning, distribution shift, France uncertainty, stale caches, leakage, or a wrong candidate set.
- Entities are treated as exchangeable bootstrap units. If a future evaluation protocol defines higher-level dependent clusters, the resampling unit should be extended deliberately rather than pretending independence.
- `bootstrap_probability_delta_gt_zero` is a descriptive bootstrap fraction, not a calibrated frequentist p-value.
- Runtime is O(replicates × entities). The current defaults are appropriate for the team's 4k–5k diagnostic sets; very large full-test resampling would need a deliberate performance review.

## Recommendation
**PROMOTE** as an independent experiment-analysis utility. Use it only when two systems have per-anchor row scores on the exact same evaluation universe. It does not authorize reuse of consumed confirmation/frozen holdouts.

## Follow-up
Wire per-anchor aggregate-safe evaluation artifacts into this utility when the benchmark/error-diff tooling exposes them, then require a paired interval for marginal integration candidates rather than comparing independent score intervals by eye.
