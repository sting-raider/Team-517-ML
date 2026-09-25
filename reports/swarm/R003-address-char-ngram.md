# R003 — Address character n-gram retriever

## Hypothesis

A complementary 3–5 character n-gram address retrieval channel may recover true S1→S2/S3 links missed by blocker v2 under address reordering, punctuation changes, partial token corruption, and spacing variation.

## Change

No production retrieval change is claimed. This run verified the live swarm state, claimed R003, created `agent/r/R003-address-char-ngram`, inspected blocker v2, and attempted to obtain the complete raw training inputs for an empirical same-anchor comparison.

## Protocol

- Base: `main@2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`
- Intended evaluation: designated calibration/development anchors only; confirmation/frozen holdout untouched
- Intended cap: 640
- Required inputs: complete `train_source1.tsv`, `train_source2.tsv`, `train_source3.tsv`, and `train_ground_truth.tsv`
- Baseline reference: confirmation pair recall 0.947246; blocking oracle macro F0.5 0.980951. These are context only and were **not** reused as an experimental comparison set.
- Drive access: verified. The shared dataset folder and train files are visible.
- Full Source-1 (210,069,713 bytes) streamed successfully into the chat runtime.
- Ground truth (127,015,583 bytes) streamed successfully into the chat runtime.
- Source-2 (489,301,488 bytes) and Source-3 (503,705,637 bytes) were rejected by the Drive connector with HTTP 413 because each exceeds the 268,435,456-byte connector transfer limit.
- Python, user-visible Python, and container execution then returned a session-level `ClientError`, so even the successfully mounted files could not be processed.

No sample was substituted for the required full target inventory.

## Results

**BLOCKED. No empirical retrieval metric is claimed.**

The experiment did not reach a valid comparison because complete S2/S3 target inventories could not be transferred into the analysis runtime and the compute backend was unavailable.

| Metric | Baseline reference | R003 |
|---|---:|---:|
| Candidate pair recall | 0.947246 | not measured |
| Blocking oracle macro F0.5 | 0.980951 | not measured |
| Entity recall | required | not measured |
| All-matches-retrieved rate | required | not measured |
| Candidate-count quantiles | required | not measured |
| US / India slices | required | not measured |
| Runtime / memory | required | not measured |

## Static inspection

Blocker v2 uses exact normalized full-name/full-address keys, name tokens, address words, adjacent address-word pairs, and number+address-word combinations, with posting lists filtered at frequency <=1000 and a score based on key type plus inverse posting frequency. An address character channel is therefore genuinely complementary rather than a duplicate of the current key family.

A naive full 3–5 gram materialization over every S2/S3 address could be very large, so the next executable run should first measure shingle count and posting-list fanout on a micro slice before creating a persistent full index.

## Error analysis

No row-level errors were analyzed because the target inventories were unavailable. The failure mode is infrastructure-only, not evidence against the hypothesis.

## Risks

- No score or recall gain can be inferred from this run.
- A future implementation must avoid candidate-cap mismatch when unioning the char channel with blocker v2.
- Confirmation anchors must stay untouched.
- Full n-gram indexes may have prohibitive row count unless grams are selectively indexed or pruned by document frequency.
- Do not use record IDs as matching evidence; hashes may only be retrieval keys.

## Recommendation

**BLOCKED / FOLLOW-UP.**

R003 remains scientifically high-value, but it should be recovered in a runtime that can access complete S2/S3 files, such as the shared Modal volume or lossless shards. Start with a micro fanout/runtime pass, then compare blocker v2 and blocker v2+address-char on the exact same fixed dev anchors.

## Follow-up

1. Materialize complete S2/S3 through Modal/shared-volume or lossless shards.
2. Run a micro 3–5 gram posting-frequency/fanout study.
3. Only if feasible, build the complementary channel and report the full retrieval metric set required by `AGENTS.md`.
