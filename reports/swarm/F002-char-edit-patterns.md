# F002 — Source-specific character/edit corruption patterns from positive pairs

**Issue:** #140  
**Branch:** `agent/r/F002-char-edit-patterns`  
**Recommendation:** **BLOCKED / HANDOFF**

## Hypothesis

Positive S1→S2/S3 links may contain concentrated, source- and country-specific character corruption patterns that can guide typo-tolerant retrieval and language-agnostic matching more effectively than generic fuzzy matching.

## Intended protocol

Use the complete supplied `train_source1.tsv`, `train_source2.tsv`, `train_source3.tsv`, and `train_ground_truth.tsv`. Reproduce repository normalization while retaining raw Unicode, join only supplied labeled positive pairs, and report edit-distance/op distributions by target source, country, and field. No confirmation/frozen holdout or external entity data.

## Execution result

**No empirical F002 metric was produced.**

Drive access was verified. File metadata and exact sizes are visible:

- `train_source1.tsv`: 210,069,713 bytes — successfully materialized.
- `train_ground_truth.tsv`: 127,015,583 bytes — below the connector limit.
- `train_source2.tsv`: 489,301,488 bytes.
- `train_source3.tsv`: 503,705,637 bytes.

The live Drive raw-download action rejects S2/S3 before transfer because each exceeds the platform's 268,435,456-byte (256 MiB) limit. The Project exposes no lossless dataset shards for `train_source2.tsv` or `train_source3.tsv`. The analysis container has no outbound DNS/network access, so it cannot independently download the shared Drive files.

The repo's existing R019a work already attempted the remaining GitHub Actions workaround: a PR-only workflow using `gdown` to fetch these exact four Drive files. That job failed before any hosted runner was allocated (runner_id 0; no steps/log blob), so duplicating that mechanism for F002 would not create new evidence.

## Validity checks

- No S2/S3 sample substituted for full-data analysis.
- No positive links fabricated or inserted.
- No external business/entity data used.
- No confirmation/frozen holdout or leaderboard feedback used.
- No F0.5/retrieval claim made.

## Risk

Running F002 on only S1 or on a truncated target sample would answer a different question and could badly mischaracterize source-specific corruption. The task requires complete target inventories.

## Recommendation

**BLOCKED / HANDOFF.** Recover F002 only when a compute path can access the complete S2/S3 TSVs, preferably the shared Modal volume or a functioning runner. The first successful run should record exact input byte sizes/hashes and then execute the full positive-pair join before interpreting any corruption distribution.
