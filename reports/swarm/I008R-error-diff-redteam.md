# I008R — Red-team of anchor-level experiment error-diff utility

## Hypothesis

I008 / PR #34 should make tiny experiment deltas safer by enforcing paired anchor universes and invariant metadata. This red-team asks whether the implementation actually fails loudly on invalid comparison inputs rather than converting malformed artifacts into plausible-looking aggregate deltas.

## Target reviewed

- PR #34: `I008: add strict anchor-level experiment diff`
- source branch: `agent/i/I008-error-set-diff`
- no challenge rows, confirmation data, or frozen holdout consumed

## Protocol

1. Reproduced and executed the authored `tests/test_error_diff.py` suite in a working Python runtime.
2. Audited `src/ber/error_diff.py` against the stated row contract and official `ber.metrics.row_score`.
3. Added adversarial synthetic probes for:
   - NaN score
   - infinite score
   - score outside the official [0,1] range
   - negative epsilon
   - negative truth cardinality
4. Checked whether malformed inputs fail loudly or instead produce internally inconsistent summaries.

## Baseline

The originating I008 agent could not execute its tests because its Python/container backend returned a session-level ClientError.

No competition metric baseline is relevant; this is an infrastructure correctness audit.

## Results

### Authored regression suite

The reproduced I008 tests pass:

```text
test_anchor_mismatch_fails_loudly ... ok
test_json_object_rows_loader_and_duplicate_guard ... ok
test_make_write_and_load_rows ... ok
test_paired_diff_and_slices ... ok
test_truth_metadata_mismatch_fails ... ok

Ran 5 tests
OK
```

This confirms the intended happy path and the currently covered mismatch guards.

### Blocking red-team finding: non-finite / invalid scores are accepted

`_coerce_row` converts `score` with `float(...)` but does not require it to be finite or within the official row-score range [0,1].

A challenger score of `NaN` is accepted and produces:

```text
entities = 1
challenger_macro_f0_5 = NaN
delta = NaN
improved = 0
regressed = 0
unchanged = 0
```

The category counts therefore sum to **0 while entities=1**. JSON rendering also permits a non-standard `NaN` literal by Python default.

An infinite score is likewise accepted and reported as an infinite macro/delta. A score of 1.5 is accepted as a +1.0 improvement even though no valid per-anchor F0.5 can exceed 1.

For a tool whose purpose is to vet tiny gains, silently accepting invalid score artifacts is a material research-integrity failure mode.

### Blocking red-team finding: negative epsilon creates contradictory classifications

`compare_rows(..., epsilon=-1e-9)` currently accepts a negative tolerance.

For an exactly unchanged row with delta 0:

```text
improved = 1
regressed = 1
unchanged = 0
```

The improved/regressed/unchanged counts sum to **2 for one entity**.

The CLI exposes `--epsilon` directly, so this is user-reachable rather than a purely internal edge case.

### Lower-severity input validation gap: negative cardinalities

Negative `truth_count` values are accepted and bucketed as `two_to_three`. Negative predicted/candidate counts are also accepted by coercion.

These should never arise from `make_rows`, but loaders explicitly accept external JSON/JSONL/TSV artifacts, so fail-loud validation is appropriate.

## What passed

The core paired-comparison logic is otherwise sound in the tested cases:

- exact anchor-universe mismatch fails by default
- `--allow-intersection` is explicit and reports dropped counts
- duplicate anchors fail
- truth/country/source invariant mismatches fail when present in both rows
- official row-score construction in `make_rows` is correct
- country/cardinality slices agree with paired arithmetic
- largest-change ordering is deterministic by absolute delta then anchor ID

## Required fix before promotion

At minimum:

1. In `_coerce_row`, require `math.isfinite(score)` and `0 <= score <= 1`.
2. Require count fields (`truth_count`, `predicted_count`, `candidate_count`) to be non-negative integers when present.
3. In `compare_rows`, require finite `epsilon >= 0`.
4. Add regression tests for all three validation classes.
5. Prefer strict JSON output (`allow_nan=False`) as a final defense so invalid floats cannot escape even if a future code path bypasses validation.

## Risks

The discovered bugs do not invalidate previously reported challenge metrics because this utility is new and not on the selected inference path.

They do block using I008 as a research-integrity guard until fixed: malformed row artifacts could make aggregate comparisons nonsensical without an exception.

## Recommendation

**FOLLOW-UP / FIX BEFORE PROMOTION.**

PR #34's core design is useful and its existing tests pass, but the loader/epsilon validation gaps should be fixed before marking the tool safe for routine use on sub-0.001 experiment deltas.

No competition-score gain is claimed.
