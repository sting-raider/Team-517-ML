# F012a — Full S1 France format-shift audit

## Hypothesis
Unlabeled French Source-1 anchors may differ materially from labeled US/India Source-1 anchors in Unicode/diacritics, tokenization, numeric/address structure, missingness, and the behavior of the current accent-stripping normalizer.

## Change
No modeling change. This was intended as a full-file descriptive audit using the complete Source-1 train and test TSVs.

## Protocol
- Issue: #20
- Branch: `agent/x/F012a-source1-france-audit`
- Intended data: complete `train_source1.tsv` (210,069,713 bytes) and `test_source1.tsv` (175,022,086 bytes).
- Current production normalizer inspected from `src/ber/data.py`: lowercase -> `strip_accents` -> replace non-letter/non-digit runs with spaces -> trim.
- No French labels and no external entity/business data.

## Result
**BLOCKED. No empirical metric or France score is claimed.**

The connected Drive can list the shared dataset and can stream both complete Source-1 files into connector-managed raw-file handles. However, in this chat session:
1. connector-produced raw handles are not visible to `files.materialize`; and
2. both available Python/container execution backends return a platform `ClientError` even for trivial commands, so the raw bytes cannot be processed programmatically.

This is an execution-runtime blocker, not a data-quality result. No sampled substitute was used.

## Evidence / capability checks
- Shared Drive folder and train/test subfolders were readable.
- Complete Source-1 and ground-truth files are below the Drive connector's 256 MiB raw-download ceiling and were accepted by the connector.
- Source-2/3 files are above that ceiling, but they are outside this bounded F012a scope.
- Production normalization code was read from current `main`.

## Risks
Any attempt to infer French distribution statistics from file metadata, connector previews, or partial text would be invalid and would violate the full-file protocol.

## Recommendation
**BLOCKED.** Recover this task in a runtime where the connector raw-file handle can be mounted into Python/container execution. The scientific question remains useful and unmeasured.

## Follow-up
On recovery, compute full-file country-stratified aggregates only; do not commit row-level records. Compare raw versus normalized non-ASCII/diacritic loss, token/digit structure, punctuation, missingness, and length quantiles for France vs US/India.
