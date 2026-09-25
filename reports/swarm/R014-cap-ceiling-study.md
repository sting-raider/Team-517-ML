# R014 — Oracle ceiling above cap 640

## Hypothesis

If blocker v2 still retrieves many true links below raw rank 640, increasing the cap to 1280/2560 should raise candidate recall and blocking-oracle macro F0.5 on the same calibration anchors. If not, future retrieval work must add new retrieval keys/channels rather than merely widening the cap.

## Change

No modeling change was made. This task attempted to reproduce the current blocker-v2 calibration benchmark and evaluate wider raw candidate caps.

## Protocol

Planned evaluation:
- deterministic 30,000-anchor development sample;
- calibration fold only, matching `reports/retrieval_study.json`;
- caps 640, 1280, 2560, plus effective unbounded blocker-v2 pool if feasible;
- identical anchors and blocker keys at every cap;
- pair recall, entity recall, all-matches-retrieved rate, blocking-oracle macro F0.5, candidate-count quantiles, US/India and S2/S3 slices, runtime/memory;
- no matcher retuning and no confirmation/final-holdout access.

Verified baseline from current main: cap-640 confirmation pair recall 0.947246 and blocking-oracle macro F0.5 0.980951. These are context only; the intended experiment was calibration-slice paired comparison.

## Execution blocker

Connected Google Drive access was verified and the shared dataset folder was enumerated. The train files are:
- `train_source1.tsv`: 210,069,713 bytes;
- `train_source2.tsv`: 489,301,488 bytes;
- `train_source3.tsv`: 503,705,637 bytes;
- `train_ground_truth.tsv`: 127,015,583 bytes.

The connector successfully streamed the complete S1 and ground-truth files into the analysis runtime, but rejects S2/S3 because each exceeds its hard 268,435,456-byte (256 MiB) transfer limit. The shared Drive folder contains no lossless ChatGPT-sized S2/S3 shards, and Drive search found none. The execution container has no direct DNS/network route to Google Drive, so the public-link fallback cannot fetch them independently.

Because blocker-v2 ranking depends on the full S2/S3 inventory and posting frequencies, replacing those files with a sample would change the experiment and invalidate any cap-ceiling claim. No sampled surrogate was run.

## Results

No new empirical metric is claimed.

| Metric | Baseline context | R014 result |
|---|---:|---:|
| Pair recall @640 | 0.947246 (confirmation) | BLOCKED |
| Blocking-oracle macro F0.5 @640 | 0.980951 (confirmation) | BLOCKED |
| Pair recall @1280/@2560 | n/a | BLOCKED |
| Oracle @1280/@2560 | n/a | BLOCKED |

## Error analysis

The failure is environmental rather than methodological:
1. The complete target inventory is mandatory because global key frequencies and rank order determine blocker output.
2. The two required target TSVs are both larger than the connector's per-file transfer ceiling.
3. No pre-sharded equivalent is currently present in Drive.
4. Sampling S2/S3 would alter both frequencies and candidate competition, producing misleading recall/oracle numbers.

## Risks

Running this experiment on a sampled target inventory would likely overstate recall and distort candidate-count distributions. Using any cached result without confirming the exact dataset/config would also violate the experiment contract.

## Recommendation

**BLOCKED** in this ChatGPT runtime until either:
- S2/S3 are made available as lossless shards below 256 MiB each, preserving exact rows; or
- the same registered experiment is executed on the team's Modal/private-volume path with the documented blocker-v2 code.

Do not treat this as evidence for or against wider caps.

## Follow-up

Prepare lossless Drive shards for `train_source2.tsv` and `train_source3.tsv` using the repository's ChatGPT dataset sharder, or recover this claim on a runtime with the shared Modal volume.