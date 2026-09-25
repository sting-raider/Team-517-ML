# R006 — BM25/IDF-weighted address retriever over blocker v2

## Hypothesis
A source-specific BM25/IDF-weighted address-token retrieval channel may recover true S1→S2/S3 links missed by blocker v2, especially when names are weak but several moderately rare address tokens survive.

## Change
No production or experiment code was changed. The task was claimed and dataset access was tested before implementation.

## Protocol
- Branch: `agent/r/R006-bm25-address`
- Issue: #71
- Intended evaluation: designated development/calibration anchors only; cap 640; no confirmation/frozen holdout.
- Successfully materialized:
  - `train_source1.tsv`: 210,069,713 bytes
  - `train_ground_truth.tsv`: 127,015,583 bytes
- Required target inventories:
  - `train_source2.tsv`: 489,301,488 bytes
  - `train_source3.tsv`: 503,705,637 bytes
- Google Drive raw-file handoff limit observed in this runtime: 268,435,456 bytes.
- S2/S3 fetches failed before action invocation with HTTP 413 because each file exceeds that limit.
- Searched Drive/Project file surfaces for prepared Source-2/Source-3 shards; none were found.

## Results
No retrieval metric was measured. In particular, this run makes **no claim** about pair recall, entity recall, all-matches-retrieved rate, blocking-oracle macro F0.5, candidate counts, or runtime of BM25 retrieval.

## Error analysis
The blocker is environmental, not scientific: address BM25 requires the target-record address text from S2/S3. Ground-truth target IDs without target text are insufficient to construct or evaluate a legal retriever.

## Risks
Using a truncated S2/S3 sample would change the candidate universe and document frequencies, invalidating comparison with blocker v2. Fabricating a metric from S1 + ground-truth IDs would be label leakage and scientifically meaningless.

## Recommendation
**BLOCKED** in this ChatGPT runtime. Reassign R006 to a worker with the shared Modal volume or provide lossless sub-256-MiB S2/S3 shards. Do not treat this as evidence for or against address BM25.

## Follow-up
Run the exact claimed experiment once complete S2/S3 target text is available, comparing blocker v2 and blocker v2 + address BM25 on identical calibration anchors.
