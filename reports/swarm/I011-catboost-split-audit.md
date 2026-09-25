# I011 — CatBoost development split and model-selection contamination audit

**Issue:** #53  
**Branch:** `agent/i/I011-catboost-split-audit`  
**Baseline audited:** main at `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`  
**Recommendation:** FOLLOW-UP

## Hypothesis

The selected CatBoost baseline could be overstated if fitting, early stopping, threshold calibration, candidate-budget selection, model-depth selection, development holdout, or confirmation evidence are mixed in a way that makes a reported score look more independent than it really is.

## Change

No matcher, blocker, threshold, feature, or submission behavior was changed. This is a Tier-0 red-team audit of the exact current selection path and its reported metrics.

The audit specifically distinguishes:

1. **direct leakage / split contamination**, which would invalidate a score; from
2. **ordinary repeated development selection**, which is allowed but makes the selected development score optimistic; from
3. **configuration-scope mismatch**, where a valid confirmation score is later quoted for a materially different cap/threshold configuration.

## Protocol

Inspected latest main source and committed artifacts:

- `src/ber/blocking.py`
- `src/ber/experiment.py`
- `src/ber/wide_evaluate.py`
- `src/ber/retrieval_study.py`
- `src/ber/tune.py`
- `src/ber/freeze_first.py`
- `src/ber/candidate_budget.py`
- `src/ber/confirm.py`
- `src/ber/predict.py`
- `modal_app.py`
- `reports/address_baseline.json`
- `reports/retrieval_study.json`
- `reports/wide_calibration.json`
- `reports/tuning.json`
- `reports/candidate_budget.json`
- `reports/confirmation.json`
- `reports/submission_v1_confirmation.json`
- `reports/data_audit.json`
- relevant Git history through main `2a2ae6e`

The shared Drive was verified. Full `train_source1.tsv` (210,069,713 bytes) can be transferred in this chat, while the 489–504 MB Source-2/3 files exceed the connector's 256 MiB raw-download ceiling. No new confirmation/frozen holdout was consumed. The local Python/container pool was unavailable in this chat (`TooManyActiveSessionsError` / `ClientError`), so this report makes no fresh executable metric claim.

## Results

### 1. Anchor partitions are disjoint by construction

The 30,000 development anchors are selected as the first 30,000 Source-1 entities under:

`ORDER BY md5('sample517:' || entity_id)`

The historical confirmation is the next 5,000 anchors (offset 30,000), and the selected 640-cap confirmation is the following 5,000 anchors (offset 35,000).

`reports/data_audit.json` records **zero duplicate Source-1 IDs** in both US and India, plus zero duplicate truth anchors. Therefore these windows cannot overlap by duplicated anchor ID.

Inside the 30,000-anchor development sample, `experiment.fold()` assigns each anchor deterministically to one of four mutually exclusive SHA256 buckets: 60% fit, 15% early stopping, 15% calibration, 10% development holdout. Candidate rows inherit the anchor group.

**Finding: PASS.** No direct anchor-fold overlap was found.

### 2. Fit and early stopping are separated correctly

`experiment.py` and `tune.py` fit CatBoost only on the `fit` anchors and pass only the `early` anchors as CatBoost's evaluation set for early stopping.

The blocker is built from the complete unlabeled S2/S3 search inventory. Ground truth is attached only after candidate generation when feature rows are materialized. This is a documented transductive search-inventory protocol, not label leakage.

**Finding: PASS.** No held-out labels are used for fitting or candidate insertion.

### 3. The 4,389-anchor calibration fold is intentionally reused for model selection

The same 4,389 calibration anchors are used for several related choices:

- threshold selection;
- raw retrieval-cap and lexical-shortlist comparisons;
- depth-8 versus depth-10 CatBoost comparison;
- later candidate-budget comparison for the final depth-10 model.

For depth 10, `reports/tuning.json` reports **0.930679 macro F0.5** on those same 4,389 anchors after choosing threshold 0.625 on that population.

This is valid development/model-selection evidence, but it is not an unbiased estimate of the selected configuration. Repeated comparisons on the same calibration fold create ordinary winner's-curse/model-selection optimism.

**Finding: CAVEAT, not leakage.** Treat calibration deltas as development evidence and replicate fragile gains before promotion.

### 4. The 3,051-anchor development “holdout” is no longer untouched

`reports/address_baseline.json` reports the 10% development holdout (3,051 anchors), including country-transfer diagnostics. Those results were visible during subsequent system iteration.

The current README correctly says repeated development-holdout results should not be presented as untouched estimates.

**Finding: CAVEAT.** The 3,051-anchor development holdout is useful diagnostic evidence, not a fresh final check.

### 5. The 0.928835 confirmation result is scoped to the exact 640-cap configuration

`freeze_first.py` freezes the selected depth-10 model with:

- threshold **0.625**
- raw candidate cap **640**
- shortlist cap **640**

`confirm.py` then loads this frozen configuration and scores the 5,000-anchor offset-35,000 confirmation window without retuning the threshold.

The committed result is:

- macro F0.5 **0.928835**
- pair recall **0.947246**
- blocking-oracle macro F0.5 **0.980951**
- singleton false-positive rate **10.65%**

**Finding: PASS for the 640-cap configuration.** Source and artifacts show no direct confirmation leakage or post-hoc threshold fit on this window.

Git history cannot independently prove wall-clock selection chronology because the initial implementation and reports were introduced together in the large baseline commit `4872bc6`. The implementation and later commit history are consistent with the documented protocol, but the repository alone is not a cryptographic execution ledger.

### 6. The later 160-cap Modal export is a different, unconfirmed configuration

After the 640-cap confirmation was recorded, the organizer clarified that smaller candidate sets are also favored in final review. `candidate_budget.py` therefore re-evaluated the final depth-10 model on the same 4,389 calibration anchors and selected smaller-cap operating points.

At cap 160, the current committed development result is:

| Metric | 640 cap | 160 cap | Change |
|---|---:|---:|---:|
| Calibration macro F0.5 | 0.930679 | 0.927197 | -0.003483 |
| Threshold | 0.625 | 0.575 | -0.050 |
| Candidate pair recall | 0.945863 | 0.925308 | -0.020555 |
| Blocking-oracle macro F0.5 | 0.981178 | 0.973081 | -0.008097 |
| Mean candidates / anchor | 442.63 | 142.18 | -300.45 (~67.9%) |

`modal_app.py` correctly rewrites the copied model config to the **cap-specific threshold 0.575**, cap 160, and shortlist 160 before scoring. So there is no threshold/cap implementation mismatch.

However, the 160-cap configuration has **not** been evaluated on the 5,000-anchor offset-35,000 confirmation as an untouched configuration. The 0.928835 number belongs to the 640-cap configuration and must not be quoted as the measured score of the 160-cap Modal export.

The README already states this distinction; this audit elevates it to a swarm-level evaluation invariant.

**Finding: FOLLOW-UP / configuration-scope risk.** The completed 160-cap export is development-selected under the organizer's candidate-count criterion, not independently confirmed at 0.928835.

## Error analysis

The main risk is not a classic train/test leak. It is **metric provenance drift** as experiments accumulate:

- a valid 640-cap confirmation number is easy to copy into a discussion of the later 160-cap output;
- the calibration fold has been queried for many thresholds, caps, shortlist modes, and model depths, so tiny gains there deserve skepticism;
- the 3,051 development holdout has already influenced understanding of the system and should not be promoted back to “untouched” status;
- the first large baseline commit bundles code and reports, so historical execution order is only partially recoverable from Git.

None of these findings invalidate the recorded 640-cap confirmation result. They do constrain what that result can legitimately support.

## Risks and limitations

- No fresh end-to-end execution was possible because this chat's Python/container pool was unavailable.
- Full S2/S3 raw files exceed the Drive connector's per-file transfer ceiling, so no full blocker rerun was attempted.
- This audit intentionally does not consume another confirmation window merely to obtain a cleaner-looking number.
- I005 (confirmation-window freeze) and I002 (cache/config provenance) are the appropriate complementary infrastructure fixes; duplicating them here would create conflict rather than safety.

## Recommendation

**FOLLOW-UP.**

1. Keep **0.928835** as the working independent confirmation result for the exact **640-cap / threshold-0.625** configuration.
2. Treat the current **160-cap / threshold-0.575** Modal export as **calibration-selected and not independently confirmed**.
3. Do not repeatedly reuse the existing confirmation windows to compare new caps. When a materially different final integration candidate is ready, consume one fresh frozen window under the I005 policy.
4. Any downstream report/PR should tie a confirmation metric to the exact model/config/candidate-cap identity rather than citing a project-wide “current score.”
5. Tiny improvements on the 4,389-anchor calibration fold should be replicated or paired-bootstrap checked before integration.

No competition score is changed by this audit; the value is preventing a valid score from silently migrating onto a different configuration.

## Follow-up tasks

- Merge/adopt I005's confirmation-window freeze before the next fresh integration check.
- Complete I002-style config/artifact fingerprinting so model, cap, threshold, blocker, and confirmation reports can be tied to exact provenance.
- At the next coordinator-approved final integration gate, evaluate the exact final candidate budget once on a fresh frozen window and record it as a new configuration-specific confirmation result.
