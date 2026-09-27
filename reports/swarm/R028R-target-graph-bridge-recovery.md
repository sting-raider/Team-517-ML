# R028R — target-target graph bridge recovery

## Hypothesis

Among true S2/S3 links missed by the INT003 cap-160 Source-1 blocker, a useful fraction may be recoverable from similarity to another true fragment for the same Source-1 entity that *was* retrieved. If large, a conservative target-target bridge could raise the blocking oracle without indiscriminately increasing every anchor's candidate budget.

## Change

No retrieval/model change was made. This recovery run first attempted to reproduce the exact R028 measurement locally from the supplied Drive TSVs and current INT003 protocol.

## Protocol

Target benchmark is the existing 4,389 INT003 calibration anchors selected by `dev30k` + `fold(i)=='calibrate'`, with the complete training S2/S3 inventory and the frozen INT003 cap-160 lexical+name-character RRF candidate definition. Labels are evaluation-only. No confirmation/frozen window or leaderboard feedback is used.

Drive access was verified against the shared dataset folder. Exact file metadata:

- `train_source1.tsv`: 210,069,713 bytes
- `train_source2.tsv`: 489,301,488 bytes
- `train_source3.tsv`: 503,705,637 bytes
- `train_ground_truth.tsv`: 127,015,583 bytes

The complete Source-1 and ground-truth files were transferred and verified at those exact byte sizes. The current Google Drive connector refuses raw-file transfer above 268,435,456 bytes; the exact `train_source2.tsv` fetch failed with HTTP 413 before invocation because 489,301,488 bytes exceeds that ceiling. `train_source3.tsv` is also above the same hard limit by metadata. The local execution environment has no authenticated Modal client/credentials and no lossless Project-file shards are currently exposed.

## Baseline

Current INT003 retrieval gate on the intended same 4,389 calibration anchors:

- candidate pair recall: 0.944357
- blocking-oracle macro F0.5: 0.980461
- India oracle: 0.969196
- US oracle: 0.987959
- mean candidates: 148.05
- hard cap: 160

These are existing committed baseline measurements, not re-measured by this blocked run.

## Result

**BLOCKED before target-side TSV parsing.** No bridge-recall statistic, oracle delta, or candidate-count delta is claimed. Replacing the complete target inventory with a sample would answer a different question and violate the task protocol, so no sample surrogate was used.

## Error analysis

The blocker is purely data-plane/runtime access:

1. Drive authorization and dataset discovery work.
2. Files below 256 MiB transfer successfully and byte sizes match Drive metadata.
3. Both required target inventories exceed the connector's 256 MiB raw-transfer ceiling.
4. No target rows were silently sampled, truncated, or substituted.
5. The repo's private Modal volume would contain a suitable full target inventory, but this chat runtime has neither the Modal package nor credentials.

## Risks

Running R028 on a sampled S2/S3 inventory would inflate apparent bridge selectivity and could materially distort both recall and fanout. A future execution must use the complete target inventory and the exact INT003 candidate pool.

## Recommendation

**FOLLOW-UP / BLOCKED.** Resume R028 on a lane with either (a) the existing authenticated `team517-business-er` Modal volume, or (b) lossless Drive/Project shards below the connector transfer ceiling. Reuse this recovered issue/branch rather than restarting the scientific question.
