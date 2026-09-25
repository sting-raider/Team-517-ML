# F003a — Source-1 rare-number retrieval-key feasibility

## Hypothesis
Distinctive numeric tokens in Source-1 business names/addresses are common enough and sufficiently selective to justify dedicated rare-number retrieval keys and rare-number agreement/conflict matcher features.

## Change
No production retrieval behavior was changed. This task is a full-Source-1 data-forensics census intended to quantify numeric-token prevalence, document frequency, country/source slices, and practical rare-token cutoffs.

## Protocol
- Task/issue: F003a / #23
- Branch: `agent/r/F003a-s1-rare-number-feasibility`
- Intended inputs: complete Drive-backed `train_source1.tsv` (210,069,713 bytes) and `test_source1.tsv` (175,022,086 bytes)
- No sampling permitted for final aggregates.
- No Source-2/3 data required for the scoped feasibility census.
- Confirmation/frozen holdout: not used.
- External identity data: not used.

### Data-access verification
Both complete Source-1 files were successfully streamed from the shared Google Drive dataset into the chat runtime:
- `/mnt/data/train_source1.tsv` — 210,069,713 bytes
- `/mnt/data/test_source1.tsv` — 175,022,086 bytes

### Execution blocker
All three available local execution paths failed before any user code ran:
1. container shell/Python: session-level `ClientError`
2. private Python runtime: session-level `ClientError`
3. user-visible Python runtime: session-level `ClientError`

This is a compute-session availability failure, not a data-access failure. No subset, sample, hand-count, or proxy statistic was substituted.

## Results
**BLOCKED.** No empirical numeric-token counts were produced, so there is no baseline/new metric and no competition-score claim.

## Error analysis
Not applicable because analysis code could not execute. The failure occurred before parsing either TSV.

## Risks
- Reporting any prevalence/DF statistic from memory, a partial connector preview, or another experiment would violate the full-data protocol.
- Source-1-only selectivity cannot establish positive-pair stability or retrieval precision; even after this census is run, R007/M003 still require target-source evidence before promotion.

## Recommendation
**BLOCKED / RECOVERABLE.** Re-run this exact task when a Python/container session is available. The complete required raw files are accessible from Drive and below the connector transfer ceiling.

## Follow-up
The first available agent with compute should recover #23 rather than create a duplicate task, run the complete census, and replace this blocked row/report with measured results.
