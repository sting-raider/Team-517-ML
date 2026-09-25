# I010 — deterministic integration harness

## Hypothesis
A disposable worktree-based harness can make combination experiments reproducible by fixing the base/ref SHAs, merge order, and benchmark command while refusing dirty caller state or merge conflicts.

## Change
Added `tools/integration_harness.py` plus synthetic tests. The harness resolves all refs to immutable commit SHAs, creates a detached temporary worktree from an explicit base, merges experiment refs in caller-specified order, runs one exact command, and emits JSON provenance/results. The caller worktree is never checked out or modified.

## Protocol
Tier 0/1 only; no challenge data and no confirmation/final holdout consumption.

Validation command:
`python -m unittest tests.test_integration_harness -v`

Executed in the ChatGPT Linux container with Python 3 and git, using temporary local repositories because outbound GitHub network access is unavailable in the container.

## Results
5/5 synthetic tests passed in 2.133 s:
- combines two non-conflicting branches and preserves caller HEAD
- aborts loudly on a merge conflict before benchmark execution
- rejects a dirty caller worktree
- records a nonzero benchmark exit code as FAIL
- rejects an empty experiment-ref list

Competition macro F0.5: not applicable. No candidate set, model, threshold, split, or holdout was changed.

## Error analysis
The main integration risks are provenance drift, merge-order ambiguity, dirty-tree contamination, and conflict handling. The harness records/resolves refs before integration and fails on the latter two. It deliberately does not fetch remote refs; callers should fetch explicitly before invoking it so network state is not hidden inside an experiment.

## Risks
- A benchmark command can still be scientifically wrong; the harness preserves the command but does not validate its semantics.
- Merge commits are created inside the disposable worktree, so tree identity is deterministic for fixed inputs but commit SHA can depend on git merge metadata.
- Combining branches that independently alter the same model/config may merge cleanly while being scientifically nonsensical; review remains required.

## Recommendation
PROMOTE as additive research-throughput infrastructure. Wire it to the standard I001 benchmark after that PR is integrated.

## Follow-up
Use the harness for the first multi-PR integration gate and store its JSON alongside the benchmark JSON.
