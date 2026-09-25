# I008G — Fail-loud validation for error-diff artifacts

## Hypothesis

The I008 error-diff utility can be made safe for routine tiny-delta auditing by rejecting malformed row artifacts and invalid tolerances before aggregation, without changing valid paired-comparison behavior.

This task directly follows the executable I008R red-team findings.

## Change

Stacked on `agent/i/I008-error-set-diff`.

`src/ber/error_diff.py` now:

- requires every loaded/compared `score` to be finite and within **[0,1]**
- requires `truth_count`, `predicted_count`, and `candidate_count` to be non-negative when present
- requires `epsilon` to be finite and >= 0
- renders CLI JSON with `allow_nan=False` as defense-in-depth

`tests/test_error_diff.py` adds regressions for:

- NaN, +inf, -inf, score < 0, score > 1
- negative truth/predicted/candidate counts
- negative, NaN, and infinite epsilon

No model, scorer, candidate generator, threshold, or challenge artifact is changed.

## Protocol

Tier-1 synthetic regression in a working Python runtime.

The original I008 authored suite was run together with the new guard tests.

No challenge rows, confirmation window, frozen holdout, or leaderboard feedback were consumed.

## Results

```text
test_anchor_mismatch_fails_loudly ... ok
test_invalid_epsilon_fails_loudly ... ok
test_invalid_score_values_fail_loudly ... ok
test_json_object_rows_loader_and_duplicate_guard ... ok
test_make_write_and_load_rows ... ok
test_negative_counts_fail_loudly ... ok
test_paired_diff_and_slices ... ok
test_truth_metadata_mismatch_fails ... ok

Ran 8 tests
OK
```

A post-fix valid-path sanity check with one unchanged singleton row produced:

```text
entities = 1
improved = 0
regressed = 0
unchanged = 1
delta = 0.0
```

The exact malformed cases discovered by I008R now raise `ValueError` before aggregation.

## Baseline

Before this patch:

- NaN challenger score could produce `entities=1` with zero categorized rows and NaN macro/delta
- infinite / >1 scores were accepted as apparent gains
- negative epsilon could classify one unchanged row as both improved and regressed
- negative cardinalities/counts were accepted

After this patch, those cases fail loudly.

No competition macro F0.5 change is applicable.

## Error analysis

The validation is intentionally located at the row-coercion/comparison boundary so it protects both direct Python callers and JSON/JSONL/TSV-loaded artifacts.

The new checks do not alter valid [0,1] score arithmetic or slice aggregation.

Remaining non-blocking considerations:

- optional metadata absent from one side still cannot be compared as an invariant; this is documented behavior rather than a score-integrity bug
- `--allow-intersection` remains intentionally explicit and should not be used for promotion comparisons
- provenance/stale-artifact protection remains I002's responsibility

## Risks

Minimal. This is fail-loud validation only.

A caller that previously relied on invalid values will now receive an exception, which is the intended behavior for a research-integrity tool.

## Recommendation

**PROMOTE** this guard patch together with I008.

With I008G applied, the specific malformed-input blockers identified by I008R are closed, and the focused suite passes 8/8.

No competition-score gain is claimed.
