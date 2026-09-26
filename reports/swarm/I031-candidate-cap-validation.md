# I031 — Enforce per-anchor candidate cap in final submission validation

## Hypothesis

The submission validator can currently accept a structurally valid `candidate_pairs.tsv`
whose per-anchor candidate count exceeds the configured model/export cap. Because the
final completion receipt records `candidate_cap` separately, this missing invariant can
allow a stale, malformed, or wrongly merged candidate file to pass the local integrity
gate even when it no longer represents the intended scoring budget.

## Change

The patch is deliberately narrow:

- `ber.validate.validate()` accepts an optional `max_candidates_per_anchor`.
- Any anchor whose unique candidate count exceeds that bound fails immediately with
  the anchor ID, observed count, and allowed count.
- Successful validation receipts now expose `max_candidates_observed` and
  `max_candidates_allowed`.
- The CLI exposes `--max-candidates-per-anchor`.
- `modal_app.score_test()` passes its already-known `candidate_cap` for complete
  single-partition exports.
- `modal_app.merge_score()` passes its already-known `candidate_cap` after merging
  partitioned exports.
- Callers that omit the option retain the previous no-cap behavior.

No candidate generation, ranking, matcher, threshold, model, or output format changed.

## Protocol

Tier 0/1 integrity test on latest `main` base
`f08c041b274e58ae900620ac714ec8a0a06f09b0`.

Data:
- no challenge rows or labels were needed;
- shared Drive access was independently verified at startup;
- no confirmation/frozen holdout, leaderboard feedback, or external entity data was used.

Static source trace:
1. before I031, `validate()` counted candidates but imposed no ceiling;
2. `score_test()` already knows `candidate_cap`;
3. `merge_score()` already knows `candidate_cap`;
4. INT003 `modal_v3.merge_prediction()` calls
   `merge_score.local(..., 160)`, so wiring the invariant at `merge_score` protects
   the selected v3 final-output boundary without touching retrieval.

Focused synthetic cases:
- exact-cap pass;
- cap+1 fail;
- duplicate-candidate semantics remain fail-loud;
- empty candidate row pass;
- omitted cap preserves legacy behavior;
- nonpositive cap rejected.

Executed command in the available local Python runtime:

`PYTHONPATH=/tmp/i031 python -m unittest discover -s /tmp/i031/tests -v`

Result: **6/6 PASS** in 0.007 s. `py_compile` also passed for the patched validator
and focused test module. Authenticated GitHub readback confirmed the checked-in branch
source and both production call sites. No GitHub Actions workflow was configured or
triggered for the branch head during this run.

## Baseline

Before I031, a candidate row containing two valid distinct candidates was accepted by
the validator regardless of an intended cap of one, because no cap argument existed.
The validator checked row order, headers, duplicate IDs, target format,
prediction-subset membership, optional target existence, and total row coverage only.

This is not evidence that the frozen INT003 export violated cap160. I029 already traced
that export to the correctly capped fused candidate boundary. It is an integrity gap:
the validator could not independently enforce the cap recorded in the completion
receipt.

## Results

| Check | Before | I031 |
|---|---|---|
| Exact-cap row | passes | passes |
| Cap+1 row with otherwise valid IDs | passes (no invariant) | **fails loud** |
| Duplicate IDs | fails | fails |
| Empty candidate row | passes | passes |
| Legacy caller with no cap argument | passes | passes |
| Production single-run validation | cap known but unchecked | cap enforced |
| Production merged-run validation | cap known but unchecked | cap enforced |
| Validation receipt observed max | unavailable | reported |

For INT003 specifically, the production merge path already receives cap **160** from
`modal_v3.merge_prediction`; after I031 that same value becomes an independently
checked output invariant.

## Error analysis

The defect is narrow but consequential:

- **Malformed merge/export:** an anchor can acquire too many candidates while all IDs
  remain valid and predictions remain a subset. The old validator reports PASS.
- **Stale artifact mix-up:** completion metadata can say cap160 while the candidate TSV
  comes from a wider run. Checksums prove file identity, not semantic agreement with
  the configured cap.
- **Duplicate candidates:** already rejected before the cap check; I031 preserves this
  behavior rather than counting duplicates as budget consumption.
- **Empty anchors:** remain valid and report an observed count of zero.
- **Ad-hoc analysis callers:** remain backward compatible when no cap is supplied.

## Risks / red-team checks

- The invariant counts the post-parse unique candidate set. Duplicate IDs are rejected
  first, so duplicates cannot hide behind the cap.
- A cap below one is rejected explicitly rather than silently treating zero as a valid
  production budget.
- The patch does not assert that cap160 is an organizer-mandated rule; it asserts that
  the exported candidate file must agree with the pipeline's own configured scoring
  budget when that budget is known.
- No metric, threshold, candidate membership, or model output changes for valid caches
  and valid exports.
- The local runtime lacked a usable full repository clone/automatic CI path, so the
  focused test used dependency-light fake DB iteration while exercising the exact
  validator logic. GitHub source readback was used to verify the committed code.
- The frozen INT003 candidate file itself was not re-read in this task; I029 already
  audited its membership boundary and completion receipt. I031 prevents future
  regressions rather than re-certifying that artifact.

## Recommendation

**PROMOTE.** This is a low-risk fail-closed integrity guard. It does not improve macro
F0.5 directly, but it prevents an invalid or mismatched candidate export from receiving
a false local PASS and makes the completion receipt more auditable.

## Follow-up

No modeling follow-up is required from I031. If the organizer validator itself later
adds a candidate-budget rule, keep this local invariant as an earlier fail-fast check
and verify both definitions agree.
