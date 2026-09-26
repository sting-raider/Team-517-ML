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
- writes output atomically;
- preserves empty TSV fields.

The recovery adds one regression test for the only high-risk path identified but not executed by the originating agent: replacing one input path with the merged output after all inputs have been read. The focused suite is now eight tests.

`AGENTS.md` documents coordinator usage while explicitly retaining the rule that experiment branches update `experiments/REGISTRY.tsv`.

## Protocol
Branch: `agent/i/I019-registry-reconciler`.

Recovery claim: 2026-09-26T01:54Z after the previous validation-blocked lease had been idle for more than eight hours.

Repository Python requirement: `>=3.11`.
Validation runtime: CPython 3.13.5.

Commands:

```bash
PYTHONPATH=. python -m unittest tests.test_reconcile_registry -v

python tools/reconcile_registry.py \
  /tmp/registry-main.tsv \
  /tmp/registry-branch-a.tsv \
  /tmp/registry-branch-b.tsv \
  --output experiments/REGISTRY.tsv
```

Additional adversarial CLI checks:
1. use one input path itself as `--output`;
2. supply conflicting rows for the same experiment ID and verify nonzero exit, no output file, and both source paths in the diagnostic.

No challenge data, model artifacts, confirmation/frozen holdouts, or leaderboard feedback are involved.

## Results
**8/8 focused tests pass.**

The unittest body completed in 0.006 s. Interpreter startup in this ChatGPT runtime emits an unrelated spreadsheet-runtime warmup warning; it does not affect the test process or exit status.

Covered cases:
1. deterministic union of disjoint registries;
2. identical duplicate deduplication;
3. conflicting duplicate-ID rejection with both source paths;
4. malformed-header rejection;
5. malformed-row rejection;
6. empty-field render/read round trip;
7. atomic replacement of an input file after reconciliation;
8. rejection of a one-input invocation at the library layer.

Adversarial CLI results:
- same-path output: exit 0; merged IDs `I001, R002` in deterministic order; temporary `.tmp` file removed after atomic replace;
- conflicting duplicate: exit 2; output file not created; error message contains the experiment ID and both conflicting source paths.

No implementation defect was found.

## Error analysis
The original blocker was compute availability, not code correctness. Recovery exercised the exact authored implementation and authored tests, then added the missing atomic-replacement regression.

Potential failure modes now covered include malformed TSV shape, duplicate-ID conflict, empty fields, deterministic ordering, one-input misuse, and same-path atomic output.

The utility intentionally does not attempt to choose between scientifically conflicting rows for the same experiment ID. That remains a hard error because silently selecting one side could erase experiment provenance.

## Interpretation
The reconciler directly addresses the measured I018 integration bottleneck without changing experiment semantics or forcing dozens of open branches to migrate to a new registry scheme.

It does not eliminate Git's textual conflict itself. It makes resolution deterministic and fail-loud: provide every complete registry version participating in the integration, union them, and stage the result.

Because it uses only the Python standard library and the repository requires Python >=3.11, the successful CPython 3.13.5 validation is within the supported runtime range.

## Risks
- The coordinator must pass **every** registry version participating in an integration. Omitting an input can still omit its unique rows.
- Conflicting metadata for one experiment ID deliberately halts and requires scientific/provenance reconciliation.
- GitHub's web merge UI does not invoke this local helper automatically.
- The tool prevents accidental conflict loss; it cannot detect an experiment row that was never written on its originating branch.

## Recommendation
**PROMOTE.**

The previously missing execution gate is now satisfied. The reconciler is safe infrastructure to merge independently: it changes no model, retrieval, threshold, candidate, or submission behavior and preserves the central registry requirement.

## Follow-up tasks
No new implementation task is required. Coordinators should use the reconciler whenever multiple registry-editing branches are integrated together.
