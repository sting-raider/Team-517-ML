# F004 — Same-address / different-business hard-negative audit

## Hypothesis
Distinct Source-1 businesses sharing the same or near-identical normalized address may form a concentrated precision-risk family, especially in dense commercial locations and India. Quantifying this family could inform hard-negative mining, address-collision penalties, and adaptive candidate handling.

## Change
No model or retrieval behavior was changed. The task was intended as a full-data forensic audit plus a deterministic aggregate-only helper.

## Protocol
- Repository baseline: `main` at `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`.
- Dataset source: shared Google Drive folder from the Team 517 Project.
- Required file: complete `train_source1.tsv`.
- Drive metadata size: **210,069,713 bytes**.
- The complete raw file transfer succeeded and the runtime reported it mounted as `/mnt/data/train_source1.tsv`.
- Repository normalization semantics were inspected in `src/ber/data.py`: lowercase, accent stripping, non-letter/digit runs replaced with spaces, trim.
- Planned aggregation was full-inventory, not sampled.

## Result
**BLOCKED — no empirical metric claimed.**

The raw Source-1 file was accessible and transferred successfully, but every available Python/container execution attempt failed before user code could run. Attempts through the private Python runtime and container runtime returned runtime/session errors, including `ClientError` and `TooManyActiveSessionsError`. Because no code executed against the file, no collision count, country slice, pair count, or address-risk statistic is reported.

This is a compute-session blocker, not a data-access blocker.

## Baseline
No F0.5 baseline is applicable to this forensic task. The comparison baseline would have been the complete Source-1 population on the same file, stratified by US/India and normalized-address collision status.

## Error analysis
No row-level or aggregate error-family analysis was performed because the compute runtime never started successfully.

## Risks checked
- No sample was silently substituted for the complete file.
- No external business/entity data was used.
- No record IDs were proposed as predictive evidence.
- No row-level challenge data is committed.
- No score or count is inferred from partial text.

## Recommendation
**BLOCKED / FOLLOW-UP.** Re-run F004 when a Python/container session is available. The Drive path itself is verified and the file is below the connector's 256 MiB transfer ceiling, so no dataset reshaping is required for this task.

## Exact handoff
1. Fetch the complete `train_source1.tsv` from the shared Drive.
2. Reproduce the `norm` macro from `src/ber/data.py` exactly.
3. Aggregate normalized-address groups with at least two distinct Source-1 entities.
4. Split groups into same-normalized-name vs multiple-normalized-name groups.
5. Report rows/groups/pair counts, group-size quantiles, US/India slices, empty/degenerate-address handling, digit/token structure, and name-similarity buckets.
6. Keep outputs aggregate-only.
