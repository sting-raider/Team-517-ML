# R020a — Full-data source-specific posting-frequency blocker

**Issue:** #92  
**Branch:** `agent/r/R020a-source-specific-frequency`  
**PR:** #97  
**Recommendation:** **BLOCKED / HANDOFF**  

## Hypothesis

The current blocker pools S2 and S3 posting frequencies before applying the
`freq <= 1000` cutoff, rare-key selection, and frequency-derived retrieval
weight. R020 showed statically that this can suppress evidence that is rare in one
target source but common in the other.

R020a asks the empirical question: **on the exact current calibration anchors, does
computing those frequencies independently for S2 and S3 improve cap-640 retrieval
recall and blocking-oracle macro F0.5 without changing the total candidate budget?**

## Exact change

The experiment keeps the production block keys, bonuses, normalized text,
same-country hashing, frequency cutoff 1000, four-rarest-key rule, scoring form,
and one final global cap of 640.

Only the frequency scope changes:

- baseline: one pooled S2+S3 posting frequency per country/key, matching blocker v2;
- variant: separate S2 and S3 posting frequencies, separate per-source rare-key
  selection and frequency weights, then the same single global top-640 ranking.

This is deliberately stronger than a synthetic R020 demonstration but narrower
than changing the production blocker.

## Protocol

Intended full-data protocol:

- development population: first 30,000 train S1 anchors by
  `md5('sample517:' || entity_id)`;
- evaluation: `calibrate` only under the repository's `fold517` SHA256 rule;
- expected anchors: **4,389**;
- expected singletons: **252**;
- inventory: complete train S2 + S3;
- ground truth: evaluation only, never candidate generation;
- candidate cap: **640** for both baseline and variant;
- no confirmation/frozen holdout;
- no sampling and no external identity evidence.

The script hard-fails unless the reproduced pooled blocker matches the committed
calibration baseline exactly:

- candidate pair recall = **0.9458627913066248**
- blocking-oracle macro F0.5 = **0.9811781091658961**

Only after those assertions pass does it calculate the source-specific-frequency
delta.

Planned diagnostics include pair/entity/all-matches recall, blocker oracle,
mean/p50/p90/p99/max candidate count, country/source slices, recovered/lost true
links, candidate-membership changes, source-selected keys absent from the pooled
selection, pooled-cutoff suppression counts, wall time and peak RSS.

## Implementation

Added:

- `experiments/r020a_source_specific_frequency.py`
- `.github/workflows/r020a-source-specific-frequency.yml`

The TSV helper intentionally constructs an actual tab byte in generated DuckDB SQL,
avoiding the double-escaping defect independently found in R005R.

Raw files are downloaded only into ephemeral worker storage and are never committed.
The workflow is now manual-only so this blocked experiment does not burn repeated
failed CI runs on later documentation commits.

Reproduction once a working full-data runner is available:

```bash
python -m pip install duckdb==1.5.5 numpy==2.3.2 gdown==5.2.0

python experiments/r020a_source_specific_frequency.py \
  --download \
  --data-dir /tmp/r020a-data \
  --db /tmp/r020a-work/r020a.duckdb \
  --out /tmp/r020a-work/r020a-result.json
```

## Execution result

**BLOCKED. No retrieval delta or F0.5/oracle gain is claimed.**

The ordinary ChatGPT data lane cannot transfer the complete target files:

- `train_source2.tsv`: 489,301,488 bytes;
- `train_source3.tsv`: 503,705,637 bytes;
- connector raw-download ceiling: 268,435,456 bytes per file.

The local Python/container backends in this chat also returned
`TooManyActiveSessionsError` / `ClientError`, so there was no local full-data
fallback.

A GitHub Actions handoff was then attempted:

1. Run **36162138314**: workflow accepted and job created, but completed
   `failure`; no usable job log was retrievable and no result artifact existed.
2. Run **36162287834**: workflow was instrumented to write stdout/stderr to
   `run.log` and upload it with `if: always()`. The job again completed
   `failure`, with **zero artifacts** and no retrievable log blob. The connector
   reports the job as completed/failure but exposes no step records.

Because even the always-upload diagnostic artifact was absent, this session cannot
determine whether the blocker is GitHub Actions account/runner provisioning,
checkout/setup, or another pre-artifact failure. It is **not valid** to attribute
the failure to the retrieval code without logs.

No smaller sample was substituted.

## Baseline

No new baseline was measured. The experiment is guarded against accepting a run
unless it reproduces the committed calibration baseline listed above exactly.

For context only, the separate selected confirmation measurement remains:

- macro F0.5: 0.928835
- US: 0.948339
- India: 0.900722
- cap-640 pair recall: 0.947246
- confirmation blocking oracle: 0.980951

Those confirmation numbers are **not** the R020a evaluation set and are not used for
tuning.

## Result / delta

No valid empirical result.

| Metric | Pooled baseline | Source-specific variant | Delta |
|---|---:|---:|---:|
| Calibration pair recall | expected 0.9458627913 | not run | n/a |
| Calibration oracle macro F0.5 | expected 0.9811781092 | not run | n/a |
| Candidate cap | 640 | 640 | 0 |
| Full-data execution | blocked | blocked | n/a |

## Red-team checks

- **No positive insertion:** candidate SQL never joins truth.
- **No ID feature:** IDs are used for deterministic sample/fold selection, joins,
  stable tie-breaking and diagnostics only.
- **Same evaluation anchors:** variant and baseline share one candidate-generation
  run and the same `anchor_truth`.
- **Same cap:** both candidate tables are globally top-640 per anchor.
- **No confirmation leakage:** only the development calibration fold is selected.
- **No silent sample:** failure is recorded instead.
- **Baseline mismatch guard:** exact committed pair-recall and oracle assertions stop
  the experiment before any variant result can be accepted.

The full script still needs an actual execution review because this chat could not
run Python at all; static inspection is not a substitute for successful execution.

## Recommendation

**BLOCKED / HANDOFF.**

This remains a high-value retrieval experiment because it tests a concrete loss
mechanism at a fixed candidate budget. Run the preserved script on an already
authorized full-data environment, preferably the project's Modal/private-volume
runner once that lane is operational, and accept the result only if the exact
baseline assertions pass.

Do not weaken the protocol to a convenience sample merely to obtain a number.
