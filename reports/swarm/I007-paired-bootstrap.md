# I007 — Paired entity-bootstrap utility for tiny deltas

## Hypothesis

Paired uncertainty over the exact same anchors can distinguish broad improvements from tiny macro-F0.5 deltas driven by a small number of entities, reducing false promotion of noisy experiments.

## Change

Added `src/ber/uncertainty.py` with:
- strict anchor-universe alignment by default, plus explicit intersection mode;
- deterministic paired entity bootstrap over per-anchor official scores;
- percentile confidence interval for candidate-minus-baseline macro delta;
- bootstrap probability that paired delta is positive;
- per-anchor win/loss/tie counts;
- exact two-sided binomial sign test over non-tied entities;
- optional country/cardinality/other metadata slices;
- TSV CLI with aggregate JSON output.

Added `tests/test_uncertainty.py` covering exact ties, uniform improvement, mismatch failure, explicit intersection, seeded determinism, slices, and sign-test edge cases.

I007F / Issue #136 subsequently hardens this canonical implementation with explicit intersection drop counts, sign-test tie-policy metadata, bounded bootstrap allocation, standard-error/method/version provenance, and additional regression tests. The I007F details live in `reports/swarm/I007F-paired-bootstrap-hardening.md`.

## Protocol

This is a Tier 0/1 research-integrity task. It does not consume development, confirmation, or leaderboard labels and does not claim a new competition score.

The utility expects one row per anchor with an already-computed official per-anchor score in [0,1]. Paired resampling draws anchor indices once per bootstrap replicate and applies them to candidate-minus-baseline deltas, preserving the experimental pairing.

Example:

```bash
python -m ber.uncertainty \
  --baseline baseline.tsv \
  --candidate candidate.tsv \
  --out paired.json \
  --slice country \
  --slice cardinality \
  --iterations 10000 \
  --seed 517
```

By default, differing anchor universes raise an error. `--intersection` is required to intentionally compare only common anchors; I007F makes the dropped-anchor counts explicit in output.

## Validation

Original synthetic kernel checks:
- identical systems produced paired delta 0 and confidence interval [0,0];
- three uniformly improved entities produced delta +1, bootstrap P(delta>0)=1, and exact two-sided sign-test p=0.25;
- mismatched anchor universes failed loudly;
- repeated runs with the same seed were identical;
- country/cardinality slice counts were correct;
- an end-to-end TSV CLI smoke test emitted overall and both requested slice families.

I007F re-ran and extended this suite; see the follow-up report for exact commands, runtime, and memory evidence.

## Baseline / result

Baseline competition metric: unchanged. The selected confirmation macro F0.5 remains 0.928835; I007 does not re-evaluate it because current committed artifacts do not contain paired per-anchor baseline/candidate score files for two competing systems.

New competition metric: none.

## Why paired, not independent

Candidate and baseline are evaluated on the same entities. Resampling their scores independently would inject artificial sampling variance and discard the covariance that makes paired comparisons powerful. I007 bootstraps the per-anchor score delta directly.

This is especially important for the official macro metric because each S1 entity contributes equally even when match-set cardinality differs. A +0.0005 macro gain can therefore come from a handful of large entity-level flips or from a broad small improvement; the mean alone does not tell us which.

## Interpretation rules

- A bootstrap interval that includes zero is evidence that the observed mean delta is fragile on that evaluation population; it is not proof of no effect.
- P(delta>0) is a resampling diagnostic, not a Bayesian posterior probability.
- The sign test discards exact ties and asks whether the remaining non-tied anchors more often improve or regress. It is useful alongside, not instead of, macro delta.
- Slice intervals are descriptive and become noisy for small slices; do not cherry-pick them for model selection.
- Repeated tuning on the same holdout is still repeated tuning. I007 quantifies sampling uncertainty; it does not turn a consumed holdout fresh again.

## Risks

- Bootstrap intervals cover entity-sampling variation inside the evaluated population, not country shift, model-selection uncertainty, stale caches, threshold leakage, or private-test shift.
- If two runs used different candidate caps, preprocessing, or anchor universes, statistical significance cannot repair the protocol mismatch.
- Intersection mode can hide missing-anchor bugs, so it is opt-in and its drop counts are reported explicitly.
- Very large evaluation sets can make naive bootstrap index matrices expensive; I007F caps sampled-index allocation while preserving deterministic paired resampling.

## Recommendation

**PROMOTE as evaluation infrastructure.**

Use I007 after I008/error-diff or any benchmark emits paired per-anchor scores. For claimed tiny gains, require the exact same anchor universe/config boundary, report the paired CI and win/loss concentration, and replicate fragile gains before promotion.

No production matcher/retrieval behavior changes.
