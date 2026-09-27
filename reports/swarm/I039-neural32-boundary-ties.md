# I039 — neural32 cap-boundary tie dependence

## Hypothesis

INT006/V5 uses target identifiers only as deterministic secondary ordering, not as model features. That is harmless when retrieval scores are distinct at a hard boundary, but an **exact score tie crossing dense top-16 or the base/final cap boundary can make candidate membership identifier-dependent**. I035 explicitly left exact cap-boundary tie prevalence as an outstanding promotion gate.

## Exact source audit

The current PR #268 head `fdff7866c4419f4fb645aa8d45a2a15696b8b729` has three relevant orderings:

1. `src/ber/dense_retrieval.py::evaluate_capped` loads the saved **top-64** ANN result from each of four target shards, appends tuples `(float(score), rowid)`, and calls `sort(reverse=True)`. Thus equal ANN scores are ordered by **rowid descending** before dense top-16 is taken.
2. `src/ber/predict_neural.py::score_partition` asks each Faiss shard for **top-16**, merges those returned rows, and again sorts `(score,rowid)` descending before keeping 16.
3. The lexical/character side pre-caps to 32 using `ORDER BY retrieval DESC, t.entity_id`, and the final dense-first union uses `ORDER BY priority, ranking DESC, t.entity_id` at cap 32. Thus equal base scores use **target entity ID ascending**.

Therefore ID/rowid cannot change membership unless a score tie reaches a hard selection boundary. The specific local-evaluation vs production ambiguity is narrower: local evaluation can see/reorder all saved top-64 rows from a shard, while production asks Faiss for 16 first. Under normal top-k semantics these are equivalent when the shard's 16th score is strictly greater than the 17th; an exact 16/17 score tie is the unresolved case.

This is not evidence that INT006 is invalid. It defines the exact condition that must be measured.

## Change

Added `src/ber/boundary_ties.py`, a dependency-light helper that:

- detects exact-score ties straddling an arbitrary cutoff;
- quantifies tie size, selected/excluded members, and maximum membership symmetric difference;
- computes label-aware true-link sensitivity bounds **for evaluation only** without using truth for ranking;
- mirrors dense-first/base-second deduplication;
- aggregates tie prevalence and tie-width diagnostics.

Added `modal_boundary_ties.py`, an aggregate-only private-volume runner that uses the existing artifacts rather than retraining anything. For each India/US calibration/holdout slice it:

- loads all four saved `*_nprobe64.npz` ANN files;
- reconstructs the exact v3 base160 channel from the supplied training inventory;
- audits per-shard dense 16/17 ties, merged dense-16 ties, base32 pre-cap ties, and the final 16-slot base-fill boundary after dense deduplication;
- verifies every ANN rowid exists in the supplied target inventory;
- reconstructs the current local INT006 candidate pool and **fails closed unless candidate-pair recall and blocking-oracle values exactly reproduce the committed INT006 metrics**;
- compares local top64-resort semantics with a saved-prefix16 production mirror;
- measures a reverse-identifier tie-order sensitivity probe without changing production defaults.

Expected parity gates are the already committed same-slice INT006 retrieval metrics:

| Fold / country | Pair recall | Blocking oracle macro F0.5 |
|---|---:|---:|
| Calibration / India | 0.9747623729924615 | 0.992386381132954 |
| Calibration / US | 0.9825594070198387 | 0.994937691471096 |
| Holdout / India | 0.9728473581213307 | 0.9914192778520664 |
| Holdout / US | 0.982076059850374 | 0.993748189818689 |

No selected retrieval, model, threshold, or submission behavior is changed.

## Executed validation in this runtime

Dependency-light focused tests executed against the authored helper:

- **9/9 PASS**
- exact crossing-tie width and truth-sensitivity bounds
- non-crossing equal-score safety
- identifier-order membership sensitivity only inside ties
- dense-priority/base dedup behavior
- post-dense base-boundary handling
- aggregate summary arithmetic
- saved-prefix tie-risk case
- no-tie tiebreak invariance
- malformed score ordering rejection

`py_compile` also passes for the helper, tests, and Modal audit runner.

## Empirical artifact gate

**BLOCKED in this chat runtime; no prevalence number is claimed.**

The exact audit requires the saved ANN arrays under the private Modal volume, e.g. `project/experiments/int005_retrieval/<country>/part*/cal_nprobe64.npz` and `hold_nprobe64.npz`, plus the private DuckDB artifact used by INT006. Those row-level artifacts are deliberately not committed to Git. This runtime has no `modal` Python package/client or authenticated Modal-volume access.

Drive access was independently verified, but it does not substitute for these trained ANN artifacts. Moreover, raw `train_source2.tsv` (489,301,488 bytes) and `train_source3.tsv` (503,705,637 bytes) exceed the live Drive connector's 268,435,456-byte raw-download ceiling. I did not replace the exact private artifacts with sampled S2/S3 data or infer tie prevalence from aggregate reports.

The runnable exact command in a lane with the existing private volume is:

```bash
modal run modal_boundary_ties.py
```

It writes `reports/i039_neural32_boundary_ties.json` locally and fails if the reconstructed INT006 candidate metrics do not match the committed baseline before reporting tie statistics.

## Risks / interpretation

- An exact tie rate of zero at all relevant boundaries would clear this specific I035 gate.
- Nonzero tie prevalence is not automatically harmful. The important quantities are changed candidate membership, true-link sensitivity, and oracle delta under label-blind alternate tie order.
- If a per-shard 16/17 tie exists, the saved top64 prefix is only a diagnostic mirror of a production top16 search. The exact production Faiss top16 query should then be rerun before asserting byte-level candidate parity.
- The reverse-ID probe is a sensitivity test, not a proposed production tiebreak.
- The development holdout is reused; this task does not choose parameters or a new tie policy from holdout performance.

## Recommendation

**BLOCKED / FOLLOW-UP in the private Modal lane.** The source-level risk is real and precisely bounded, and the audit needed to settle it is now executable with parity guards. Do not change the neural32 candidate policy based on this task until the exact saved-artifact run measures nontrivial boundary exposure.
