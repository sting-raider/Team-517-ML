# D011 — Source1-only singleton prior feasibility

## Status

**BLOCKED / FOLLOW-UP. No empirical singleton metric is claimed.**

The supplied Drive dataset is accessible. The complete `train_source1.tsv` (210,069,713 bytes) and `train_ground_truth.tsv` (127,015,583 bytes) were streamed successfully into this ChatGPT runtime. The experiment could not be executed because the chat's Python/container execution pool was unavailable (`ClientError` / `TooManyActiveSessionsError`), and a temporary branch-only GitHub Actions fallback failed before GitHub allocated a runner (`runner_id=0`, zero executed steps). The failed workflow was removed from the branch.

This is an execution-lane blocker, not a data-access blocker and not a negative modeling result.

## Hypothesis

Source-one observables that do not depend on S2/S3 retrieval — country, name/address missingness, lengths, token/digit/punctuation statistics, Unicode character mix, and corpus frequency of normalized names/addresses — may contain held-out signal for whether an anchor has zero true S2/S3 matches. If so, that signal can become a prior inside a later score-aware singleton gate (D001), especially for the current India singleton false-positive weakness.

## Change

Added `tools/experiments/d011_singleton_prior.py`.

The helper:

- streams the complete supplied Source 1 and ground-truth TSVs;
- reproduces the repo's hash ordering with `md5('sample517:' + entity_id)`;
- uses only the first 30,000 development anchors and explicitly guards the next 5,000 confirmation IDs from overlap;
- reproduces the existing `fold517` SHA-256 split (60% fit / 15% early / 15% calibration / 10% holdout);
- computes full-Source-1 normalized name/address frequencies for the selected development anchors;
- fits a fixed small CatBoost classifier with no record IDs as features;
- compares it with global- and country-prior baselines;
- reports ROC-AUC, average precision, Brier score, log loss, country slices, and holdout precision/recall at thresholds chosen on the calibration fold for >=80%, >=90%, and >=95% singleton precision;
- contains a synthetic `--self-test` path.

It deliberately does **not** consume S2/S3 data and does **not** claim end-to-end macro F0.5 improvement. That requires combining the prior with out-of-fold candidate/matcher evidence.

## Protocol

Intended command:

```bash
python tools/experiments/d011_singleton_prior.py \
  --source1 /path/to/train_source1.tsv \
  --truth /path/to/train_ground_truth.tsv \
  --out /tmp/d011.json
```

Data:
- complete `train_source1.tsv`;
- complete `train_ground_truth.tsv`;
- development anchors = first 30,000 anchors under the existing `sample517` MD5 ordering;
- confirmation guard = offsets 30,000–34,999, identified only to assert disjointness;
- no confirmation score is computed or used for model/threshold selection.

Seed/config:
- CatBoost seed 517;
- depth 5;
- learning rate 0.04;
- at most 350 trees;
- early stopping only on the early fold;
- conservative singleton thresholds selected only on calibration.

## Baseline

The repository's current selected end-to-end confirmation baseline is 0.928835 macro F0.5, with singleton false-positive rate approximately 10.65% overall and 13.51% for India. Those are context only: D011 does not have a comparable end-to-end metric because the experiment could not run and because Source1-only singleton prediction is only a component diagnostic.

The experiment's direct baselines would be:
1. global singleton prevalence learned from the fit fold;
2. country-specific singleton prevalence learned from the fit fold.

## Results

No valid result.

Verified execution facts:
- Drive root and train folder are readable.
- `train_source1.tsv`: 210,069,713 bytes, streamed successfully.
- `train_ground_truth.tsv`: 127,015,583 bytes, streamed successfully.
- `train_source2.tsv`: 489,301,488 bytes and `train_source3.tsv`: 503,705,637 bytes remain above the chat raw-download ceiling observed by other agents, but D011 does not require them.
- Local Python/container execution was unavailable for even a trivial probe.
- A GitHub Actions fallback run (run 36158879942) ended before runner allocation: `runner_id=0`, no job steps. Therefore no self-test, download step, or experiment step ran in CI.
- The temporary workflow was removed after this diagnostic.

## Error analysis

There is no model output to analyze. The useful diagnostic is infrastructural: small/medium Drive files can reach the chat filesystem, but concurrent local execution capacity is currently the limiting resource. This differs from R001/R002, where S2/S3 transfer size itself blocked the experiment.

The D011 helper is intentionally bounded to Source 1 + truth so it remains a low-cost recovery task for the next runtime with available Python/container capacity.

## Risks

- A Source1-only singleton prior may exploit labeled-country prevalence differences that do not transfer to France. Any future integration must keep a robust unknown-country default.
- Corpus-frequency features are derived only from supplied Source 1 records, which is compliant, but the final singleton decision must still distinguish “true singleton” from “retrieval failure.”
- Confirmation labels must remain outside fitting and threshold selection. The helper guards confirmation IDs and does not compute confirmation metrics.
- Even a strong singleton classifier does not imply an end-to-end F0.5 gain. It must be tested jointly with out-of-fold retrieval/matcher scores because incorrectly suppressing a non-singleton can be costly.

## Recommendation

**FOLLOW-UP when an execution lane is available.** Run the committed helper unchanged first. Promote the signal into D001 only if it beats the prevalence baselines on the held-out development fold and retains useful precision in both US and India. Otherwise reject Source1-only singleton priors and focus D001 on matcher-score/candidate-context features.

## Handoff

Issue: #25  
Branch: `agent/d/D011-source1-singleton-prior`  
Experiment helper commit: `905904e3bf6de6d6cf77b2216da0e7b501a007e2`

No raw records, predictions, model binaries, or private row-level diagnostics are committed.
