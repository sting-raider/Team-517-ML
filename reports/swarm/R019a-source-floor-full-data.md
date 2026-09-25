# R019a — Full-data source-floor retrieval at fixed cap 640

**Issue:** #126  
**Branch:** `agent/r/R019a-source-floor-full-data`  
**PR:** #133  
**Recommendation:** **BLOCKED / HANDOFF**

## Hypothesis

The production blocker applies one global cap across S2 and S3. R019 proved synthetically that one source can crowd the other out. R019a was intended to test whether reserving a tiny per-source floor (1/2/4/8 candidates) at the same total cap 640 recovers true links and raises blocking-oracle macro F0.5 on the exact established calibration anchors.

## Exact change

Added `tools/r019a_source_floor.py`, a bounded full-data benchmark that:

- selects the same 30,000 deterministic development anchors and the same 4,389 calibration fold;
- reproduces blocker-v2 normalization, block keys, pooled S2+S3 posting frequency, rare-key selection, retrieval score, global cap, and entity-id tie break;
- materializes only target postings whose hash is queried by calibration anchors, while scanning the complete S2/S3 inventories for their exact pooled frequencies;
- compares the legacy joint cap against source floors 1/2/4/8 at fixed cap 640;
- reports pair/entity/all-matches recall, blocking-oracle macro F0.5, candidate counts, US/India slices, S2/S3 positive recall, source-starvation counts, and positive-edge deltas;
- refuses to interpret variants unless the reconstructed baseline exactly matches the committed cap-640 calibration metrics to 1e-12 and candidate-count quantiles exactly.

A PR-only workflow downloads the four user-supplied training TSVs into `/tmp` on an ephemeral worker, verifies exact byte sizes, runs the benchmark, and uploads only the aggregate JSON. Raw challenge data are never committed.

## Protocol and baseline guard

Expected exact baseline from current committed reports:

- anchors: **4,389**
- pair recall: **0.9458627913066248**
- entity recall: **0.9454912308973222**
- all-matches-retrieved: **0.8411892675852066**
- blocking-oracle macro F0.5: **0.9811781091658961**
- candidate p50/p90/p99/max: **597 / 640 / 640 / 640**

No confirmation or frozen holdout was touched.

## Execution result

**No full-data metric was produced.**

The connected Drive was verified and complete file metadata are available. S1 and ground truth can be mounted locally, while S2/S3 exceed the chat connector's 256 MiB raw-transfer ceiling. Both local execution backends (container and Python, including the user-visible Python backend) returned platform `ClientError` even for trivial commands.

To avoid silently sampling S2/S3, the task was moved to an isolated GitHub Actions worker. PR #133 triggered workflow run **36163971187**, job **108167088033**. GitHub accepted the workflow but the job failed before a hosted runner was allocated:

- run status: completed / failure
- job lifetime: ~2 seconds
- runner_id: 0
- runner_name: empty
- steps: empty
- no job log blob was produced (log fetch returned BlobNotFound)

That is an execution-infrastructure failure, not evidence for or against the source-floor hypothesis.

## Leakage / validity checks

- No external business/entity data used.
- No record IDs enter retrieval as predictive evidence; IDs are used only for deterministic split/tie semantics already present in production.
- No positives are inserted into candidate lists.
- No candidate cap change: every variant is capped at 640.
- No threshold/matcher tuning.
- No confirmation/frozen holdout use.
- The benchmark has a fail-closed exact baseline-parity guard, so a memory-saving reconstruction cannot be mistaken for the production blocker if semantics drift.

## Risks

The benchmark code has not executed end-to-end because no compute backend accepted the job. Therefore:

- no retrieval gain or loss is claimed;
- no runtime/memory figure is claimed;
- no source-floor value should be promoted into production;
- the workflow itself should remain experimental until it gets one successful parity run.

## Recommendation

**BLOCKED / HANDOFF.**

The task remains high-value because R019 already established the mechanism and the proposed test preserves the total candidate budget. Recover it on the shared Modal volume or any full-data runner that can access the supplied TSVs. First require exact cap-640 baseline parity; only then inspect floors 1/2/4/8. Promote only a floor that improves oracle/recall without candidate growth and without a meaningful country/source regression.
