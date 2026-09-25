# I008 — Anchor-level experiment error-set diff

## Hypothesis

A strict paired diff over per-anchor evaluation scores will make small experiment deltas easier to trust or reject by exposing which entities improved or regressed and whether the change is concentrated in one country/cardinality slice. It should also catch a common invalid-comparison failure: two runs evaluated on different anchor universes.

## Change

Added `src/ber/error_diff.py` with:

- `make_rows(...)` to create a deterministic row artifact from the exact truth/prediction/candidate mappings already used by the official entity-level scorer.
- JSONL / JSON / TSV row loaders.
- strict duplicate-anchor and anchor-universe checks.
- invariant checks for country/source/truth cardinality across paired runs.
- paired macro F0.5 delta, improved/regressed/unchanged counts, country/source/cardinality slices, and largest absolute anchor changes.
- `--allow-intersection` only as an explicit non-paired diagnostic escape hatch.
- a CLI: `python -m ber.error_diff BASELINE_ROWS CHALLENGER_ROWS [--out diff.json]`.

Added `tests/test_error_diff.py` covering paired slices, universe mismatch, metadata mismatch, official row-score construction, serialization, and duplicate-anchor rejection.

The utility deliberately consumes compact per-anchor row artifacts instead of raw challenge records, so it does not create another data/cache format or depend on record IDs as model features.

## Protocol

Tier 0/1 infrastructure task against main branch state at claim time.

Input row contract:

- required: `anchor`, `score`
- optional: `country`, `source`, `truth_count`, `predicted_count`, `candidate_count`

`make_rows` is the preferred producer because it computes `score` using the repository's existing `ber.metrics.row_score`, preserving official per-anchor F0.5 semantics.

No confirmation window, leaderboard feedback, raw S2/S3 data, or model threshold was used.

## Results

No competition metric is claimed. The deliverable is a comparison guard/tool.

Static review evidence:

- the diff is paired by anchor ID and refuses mismatched universes by default;
- truth cardinality/country/source mismatches are treated as invariant failures when present in both inputs;
- the overall delta is the mean of per-anchor score deltas, which is algebraically identical to challenger macro F0.5 minus baseline macro F0.5 on an identical universe;
- country and cardinality slices are computed from the same paired anchors;
- largest changes are deterministic (absolute delta, then anchor ID).

The current ChatGPT Python/container execution backend returned `ClientError` during this session, so the authored unit tests were **not executed here**. This report therefore does not claim a passing test run.

## Error analysis

The tool directly targets four research failure modes:

1. **Slice mismatch:** a run silently changes the evaluated anchor set. Default behavior is failure.
2. **Truth/context mismatch:** a supposedly paired run has different truth cardinality or immutable slice metadata. Behavior is failure.
3. **Concentrated tiny gain:** aggregate improvement comes from a narrow country/cardinality bucket while another bucket regresses. The slice table exposes it.
4. **Outlier-driven gain:** a small number of anchors dominate the delta. `largest_changes` exposes them for follow-up.

It does not diagnose *why* a row changed; agents should join the listed anchors to their own local candidate/provenance diagnostics.

## Risks

- Agents must export row artifacts from the exact candidate/prediction set being scored. A stale row artifact can still mislead; I002 is the separate cache-provenance task.
- Optional metadata absent from either input cannot be sliced.
- `--allow-intersection` can hide a universe mismatch if used casually, so it is intentionally opt-in and reports dropped counts/examples.
- Unit tests remain unexecuted in this runtime because the execution backend failed before this task began.

## Recommendation

**FOLLOW-UP.** The implementation is self-contained and safe to review independently, but run `python -m unittest tests.test_error_diff` (or the repository test suite) in a working Python/CI runtime before promotion/merge.

## Follow-up tasks

- Add row-artifact emission to the standard benchmark/experiment runner once I001 settles its output schema, avoiding duplicate schema work.
- Use I008 on every claimed sub-0.001 improvement before promotion to show paired anchor deltas and slices.
