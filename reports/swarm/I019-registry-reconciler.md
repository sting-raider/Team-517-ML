# I019 — Deterministic experiment-registry conflict reconciler

## Hypothesis
A small deterministic n-way reconciler can preserve the existing requirement that every empirical branch updates `experiments/REGISTRY.tsv` while making concurrent registry-row conflicts safe and mechanical to resolve.

I018 / Issue #157 measured the motivating pressure: 67 of 68 open PRs (98.53%) modified the same central registry, and representative unrelated branches all inserted their row at the identical post-header hunk.

## Change
Added `tools/reconcile_registry.py`, a stdlib-only registry union utility.

Behavior:
- requires two or more complete `REGISTRY.tsv` inputs;
- requires the exact canonical 15-column header;
- requires exactly 15 columns for every data row;
- requires a non-empty `experiment_id`;
- unions rows by `experiment_id`;
- silently deduplicates only identical duplicate rows;
- fails loudly if the same experiment ID has conflicting row contents, naming both input paths;
- emits rows in deterministic lexicographic experiment-ID order;
- writes the output atomically;
- preserves empty TSV fields.

Added `tests/test_reconcile_registry.py` with seven focused cases:
1. deterministic union of disjoint registries;
2. identical duplicate deduplication;
3. conflicting duplicate-ID rejection with source paths;
4. malformed-header rejection;
5. malformed-row rejection;
6. empty-field render/read round trip;
7. rejection of a one-input invocation at the library layer.

Updated `AGENTS.md` with coordinator usage while explicitly retaining the rule that experiment branches must update `experiments/REGISTRY.tsv`.

## Protocol
Branch: `agent/i/I019-registry-reconciler`.

Expected validation command:

```bash
python -m unittest tests.test_reconcile_registry -v
```

Expected coordinator usage:

```bash
python tools/reconcile_registry.py \
  /tmp/registry-main.tsv \
  /tmp/registry-branch-a.tsv \
  /tmp/registry-branch-b.tsv \
  --output experiments/REGISTRY.tsv
```

No challenge data, model artifacts, confirmation/frozen holdouts, or leaderboard feedback are involved.

## Results
Implementation and tests are committed.

**Execution validation is BLOCKED in this chat runtime.** A fresh retry after implementation returned a platform `ClientError` before even `print("compute-ok")` executed. Earlier in the same session the private Python, container, and visible-Python surfaces all failed before user code execution. Therefore no false claim of passing tests is made.

Static contract review:
- canonical header exactly matches current `experiments/REGISTRY.tsv`;
- output union is deterministic;
- the tool never chooses one conflicting experiment row over another;
- current central-registry workflow remains valid;
- challenge/model semantics are untouched.

## Error analysis
The remaining uncertainty is executable validation, not an identified logic failure.

The highest-risk cases are covered by authored tests but have not run here:
- CSV/TSV newline behavior on the repository's Python 3.12 environment;
- import/discovery behavior for `tools.reconcile_registry`;
- atomic overwrite behavior when `--output` is also one of the input paths.

The implementation reads all inputs before writing the output, so same-path output is intended to be safe, but that path should still be exercised before promotion.

## Interpretation
The reconciler directly addresses the measured I018 integration bottleneck without changing the experiment-record contract or requiring 67 existing PRs to be rewritten.

It does not eliminate Git's textual conflict itself. Instead it makes conflict resolution deterministic and fail-loud: export each complete side, run the union, stage the result. That is the smallest backward-compatible mitigation available under the current central-registry requirement.

## Risks
- Tests were not executable in this chat because the platform compute backend is unavailable.
- This utility is only safe if coordinators pass every registry version participating in the integration; omitting one input can still omit its unique rows.
- Conflicting metadata for the same experiment ID intentionally stops the merge and requires human/scientific reconciliation.
- GitHub's web merge UI will not invoke this local helper automatically.

## Recommendation
**FOLLOW-UP / VALIDATE, THEN PROMOTE.**

Run the seven focused tests in any healthy Python 3.12 environment. If they pass, this is safe infrastructure to merge independently because it changes no model/retrieval/scoring behavior and preserves the central registry contract.

## Follow-up tasks
No new task is needed unless execution exposes a defect. The immediate follow-up is validation of this PR in a healthy runtime.
