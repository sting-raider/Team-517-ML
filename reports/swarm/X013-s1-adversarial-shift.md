# X013 — Same-country Source-1 adversarial train-vs-test shift audit

## Hypothesis
A language-agnostic Source-1 character n-gram domain classifier may detect same-country train-vs-test text-format shift that coarse aggregate audits miss. Such a signal would be a robustness diagnostic, not test labels and not a leaderboard-tuning target.

## Change
No production change. The task preregistered a deterministic US/India train-vs-test adversarial-validation audit with structural baselines, character n-gram views, and a label-shuffle/null control.

## Protocol
- Intended population: complete supplied `train_source1.tsv` and `test_source1.tsv`.
- Drive access verified.
- Complete raw files transferred successfully:
  - train_source1.tsv: 210,069,713 bytes
  - test_source1.tsv: 175,022,086 bytes
- No S2/S3 records, record IDs as predictive evidence, match labels, confirmation/frozen holdouts, external entity data, France pseudo-labels, or leaderboard feedback were used.
- Current production normalization was grounded from `src/ber/data.py`: lowercase + accent stripping + non-letter/non-number collapse + trim.

## Result
**BLOCKED before row processing.**

After the complete files were transferred into the analysis environment, every available local compute surface failed before executing even a trivial probe:
- container Python: session-level `ClientError`
- private Python: session-level `ClientError`
- user-visible Python: session-level `ClientError`

A direct network fallback from the compute sandbox was also unavailable because DNS/network access is disabled there. No sample surrogate was substituted and no AUROC/AUPRC/domain-shift metric is claimed.

The Google Drive connector itself remains functional for files below its 256 MiB ceiling; the blocker here is the execution pool, not dataset authorization.

## Error analysis
No model errors can be analyzed because the classifier never executed. The failure occurred before parsing the transferred TSVs.

## Risks
Reporting a sampled or invented domain-separability result would violate the experiment contract. The public-leaderboard/local gap must not be treated as row-level supervision.

## Recommendation
**BLOCKED / FOLLOW-UP.** Recover this exact experiment only in a chat/runtime with a working Python/container lane. The raw Source-1 files fit the connector ceiling, so no alternate data source is required.

## Follow-up
When recovered, keep the preregistered null controls and same-country design. Do not broaden the task into France pseudo-labeling or leaderboard-driven tuning.
