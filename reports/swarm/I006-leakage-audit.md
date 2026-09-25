# I006 — Leakage / split / candidate contamination audit

**Issue:** #11  
**Branch:** `agent/i/I006-leakage-audit`  
**Baseline audited:** main at `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`  
**Recommendation:** FOLLOW-UP

## Hypothesis

The current confirmation score could be artificially optimistic if identifiers or labels enter learned features, positives are inserted into blocked candidates, development/confirmation anchors overlap, confirmation is reused for selection, candidate-cap semantics differ between evaluation and inference, or stale caches silently mix incompatible experiment states.

## Change

No model, blocker, threshold, normalization, or prediction behavior was changed. This task is a red-team audit.

A focused regression test was added at `tests/test_leakage_guards.py` to lock two high-value invariants:

1. the learned feature function accepts only normalized pair text plus retrieval evidence/source and exposes exactly 47 features;
2. adding a ground-truth link does not make an otherwise unretrievable target appear in `blocking.candidates`.

## Protocol

Audited the current implementations in:

- `src/ber/features.py` and `src/ber/fast_features.cpp`
- `src/ber/blocking.py` and `src/ber/shortlist.py`
- `src/ber/experiment.py`, `src/ber/tune.py`, `src/ber/wide_evaluate.py`
- `src/ber/confirm.py`, `src/ber/freeze_first.py`, `src/ber/predict.py`
- `src/ber/metrics.py` and `src/ber/data.py`

Cross-checked the selected reports:

- `reports/tuning.json`
- `reports/retrieval_study.json`
- `reports/submission_v1_confirmation.json`
- `reports/data_audit.json`

Also inspected repository history from the baseline-building commit `4872bc6` through current main to distinguish model/evaluation changes from later inference, Modal, and swarm-orchestration changes.

Drive access was verified against the shared challenge folder. The live connector can stream files below 256 MiB, but rejects the complete 489,301,488-byte `train_source2.tsv` and 503,705,637-byte `train_source3.tsv`. Therefore this audit does **not** claim a fresh full-data score. The local Python/container execution backend also returned an infrastructure `ClientError` during this session, so the newly added regression test could not be executed here; it is intentionally small and reproducible with:

```bash
PYTHONPATH=src python -m unittest tests.test_leakage_guards -v
```

No sample was substituted for a full-data empirical claim.

## Results

The selected reference remains the recorded 5,000-anchor confirmation result: macro F0.5 **0.928835**, pair recall **0.947246**, blocking-oracle macro F0.5 **0.980951**, singleton false-positive rate **10.65%**. This audit found no evidence requiring those numbers to be discarded.

| Audit class | Result | Evidence |
|---|---|---|
| Record ID / country / label in matcher features | **PASS** | `features()` consumes only two normalized name/address pairs plus retrieval score, key-hit count, and source. `FEATURE_NAMES` contains 47 numerical comparison/retrieval features and no IDs, country categories, truth, or labels. Native C++ path mirrors the same 7 inputs / 47 outputs. |
| Ground-truth-aware candidate insertion | **PASS** | `blocking.candidates` depends only on anchor text/country-derived retrieval keys and the unlabeled S2/S3 index. The `truth` table is not referenced. Labels are attached later in `experiment.materialize` after candidate construction. |
| Label-aware shortlist / pruning | **PASS** | `shortlist.py` uses pairwise name/address similarities. Candidate entity ID is only a deterministic tie-breaker, not a learned feature or similarity signal. |
| Development fold leakage | **PASS** | Fit / early-stop / calibration / holdout are deterministic disjoint SHA256 buckets of the S1 anchor ID. Every candidate row inherits its anchor's fold. |
| Confirmation anchor overlap | **PASS** | `confirm.py` explicitly checks confirmation IDs against the model's saved development `anchors.json` and raises on overlap. The selected submission report uses 5,000 hash-ordered anchors at offset **35,000**, separate from the 30,000-anchor development sample and earlier confirmation range. |
| Confirmation used for threshold/model selection | **PASS from source/history audit** | Depth-10 selection and threshold 0.625 come from the 4,389 calibration anchors. `freeze_first.py` freezes that configuration before confirmation; `confirm.py` loads the saved threshold without retuning it. Later commits through audited main primarily add inference/Modal/swarm machinery rather than replacing the learned selection protocol. |
| Candidate-cap boundary | **PASS for selected v1** | `submission_v1_confirmation.json` records raw cap 640 and shortlist cap 640. `predict.score_batch` exports `considered`, i.e. exactly the rows that reach matching after optional shortlist. The cap-sweep report explicitly labels its thresholds as calibration results, not independent confirmation. |
| Full-inventory use across folds | **PROTOCOL CAVEAT, not label leakage** | All S2/S3 records remain available as unlabeled retrieval inventory in every anchor fold. This is documented and matches the transductive search-inventory protocol, but it is not a purely inductive record-level split. No held-out positive labels are injected. |
| Feature/candidate/index cache provenance | **FAIL / HIGH research-integrity risk** | Multiple caches can be reused based on existence or a coarse integer version without hashes tying them to raw inputs, code/config, anchor set, candidate cap, or blocker settings. This can silently create stale/mismatched experiment comparisons. |

## Cache-provenance failure modes

The audit found several concrete ways stale state can survive without a loud failure:

1. `experiment.run` reuses `features.npz` and `anchors.json` whenever they exist unless `--refresh` is passed. No feature-code hash, DB/input fingerprint, candidate-table identity, blocker version, or cap is verified.
2. `data.prepare` reuses a train/test table once sources `{1,2,3}` are present. It does not verify that those tables came from the currently supplied TSV bytes or current normalization code.
3. `blocking.build_index` reuses an index solely when `index_versions.version == 2`. The indexed table contents and `block_keys` implementation are not fingerprinted.
4. `wide_evaluate.py` materializes features from a persistent `wide_candidates` table produced by a separate retrieval-study step. It does not verify candidate-table provenance, anchor identity, blocker config, or cap before trusting that table.
5. `tune.py` skips a completed depth trial when the report, model, and probability file exist. It does not verify that the saved model/probabilities correspond to the currently loaded feature arrays.
6. `predict.py` has stronger output-resume protection through model SHA256, config equality, and shard checksums, but the database is identified by resolved path rather than content hash and it inherits the coarse retrieval-index reuse rule.

These are not evidence that the recorded 0.928835 score is wrong. They are evidence that future swarm experiments can accidentally compare different underlying states while believing they are paired.

## Error analysis

The dangerous pattern is asymmetric: the selected historical result has several independent sanity checks, while rapid follow-up experiments are more exposed.

- A feature change with an old `features.npz` can produce a result that is neither the old nor intended experiment.
- A blocker change with an old version-2 index can silently keep old postings.
- A regenerated `wide_anchors` table with a stale `wide_candidates` table can cause calibration features to come from the wrong candidate provenance.
- A rerun of `tune.py` can report an old completed model even after upstream features changed.

Because the swarm is explicitly hunting small gains, this class of bug is especially costly: a +0.0003 that comes from stale state is indistinguishable from leaderboard perfume unless provenance is enforced.

## Risks and limitations

- The audit is primarily source- and artifact-level. Raw S2/S3 files exceed the connector's per-file transfer ceiling, so a fresh end-to-end rerun was not possible in this chat.
- The new regression test was written but could not be executed because the Python/container backend returned a session-level `ClientError`. No passing test result is claimed.
- Git excludes model binaries and local feature arrays by design, so historical artifact provenance cannot be cryptographically reconstructed from the repository alone.
- The use of the complete S2/S3 inventory across anchor folds is transductive with respect to text availability. It is documented and does not expose held-out match labels, but reported validation should continue to describe that protocol precisely.

## Recommendation

**FOLLOW-UP.** Keep the current 0.928835 confirmation baseline as the working reference; this audit found no direct leakage or positive injection that invalidates it.

Immediately harden cache provenance before trusting a large wave of tiny-delta experiments. The minimum useful fix is to hash or otherwise fingerprint the raw/input table identity, feature schema/code/config, anchor IDs, blocker/index configuration, candidate cap, and upstream artifact hashes, then fail loudly on mismatch. This belongs in the existing I002 backlog lane rather than being smuggled into this audit as an unmeasured refactor.

## Follow-up tasks

- **I002:** implement experiment/config fingerprints and stale-cache rejection for DB tables, retrieval indexes, feature arrays, `wide_candidates`, tuned probabilities, and output manifests.
- Add this leakage guard test to the normal test suite once an execution-capable worker picks up I002 or integration work.
