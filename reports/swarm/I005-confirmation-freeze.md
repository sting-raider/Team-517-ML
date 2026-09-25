# I005 — Freeze consumed confirmation windows

## Hypothesis

Recording already-inspected confirmation ranges and requiring explicit, reasoned overrides for either reuse or fresh holdout consumption will reduce accidental confirmation-set tuning and repeated evaluation.

## Change

Added a confirmation-use policy layer without changing retrieval, features, matcher scores, thresholds, or the official metric:

- `reports/CONFIRMATION_FREEZE.json` records the development reservation and the two already-consumed 5,000-anchor confirmation windows.
- `src/ber/holdout.py` validates confirmation windows, rejects development overlap, rejects silent reuse, rejects partial overlap with consumed windows, and requires an explicit reason for either exact reuse or fresh consumption.
- `src/ber/confirm.py` now requires explicit `--offset` and `--size`, refuses to overwrite a report unless explicitly requested, and invokes the holdout guard before reading confirmation labels.
- A successful fresh-window evaluation appends a consumption receipt to the freeze manifest, including config/result hashes and UTC time.
- `README.md` no longer runs `ber.confirm` as part of routine reproduction.
- `tests/test_holdout.py` covers the policy boundary.

## Protocol

Tier 0/1 infrastructure and red-team task. No new confirmation labels were evaluated.

The repository was audited for all confirmation artifacts and current confirmation code. Two prior confirmation windows were found from committed reports:

1. Offset **30,000**, size **5,000**: historical shortlist confirmation in `reports/confirmation.json`, macro F0.5 **0.9147589909**.
2. Offset **35,000**, size **5,000**: selected first-submission confirmation in `reports/submission_v1_confirmation.json`, macro F0.5 **0.9288349532**.

The first **30,000** hash-ordered source-one anchors are already used for development/model selection and are marked forbidden for confirmation.

The new guard was exercised with focused standard-library unit tests. `confirm.py` and `holdout.py` were syntax-compiled. No S2/S3 data or model inference was needed because this task deliberately did not consume any holdout.

## Results

- **9 / 9 holdout-policy tests passed**.
- Syntax compilation passed for the modified confirmation path.
- Existing consumed windows are explicitly frozen at **[30,000, 35,000)** and **[35,000, 40,000)**.
- The development region **[0, 30,000)** is permanently rejected as a confirmation window.
- Exact reuse of a consumed window now requires `--allow-reuse` and a non-empty `--reason`.
- Partial overlap with a consumed window is rejected even with the reuse override.
- A fresh disjoint window is rejected unless `--consume-new` and a non-empty `--reason` are supplied.
- Successful fresh consumption updates the manifest atomically with config/result hashes.
- Existing report paths are protected from accidental overwrite by default.
- Routine README reproduction no longer executes confirmation evaluation.
- **No new macro F0.5, retrieval recall, or confirmation score was generated.**

Implementation tip: this change intentionally makes `python -m ber.confirm` fail closed unless the caller states exactly which confirmation window is being used and why.

## Error analysis

The audit found two concrete contamination hazards in the previous workflow:

1. `ber.confirm` defaulted to offset 30,000 / size 5,000, which is already the historical confirmation sample. A routine invocation therefore silently reused an inspected holdout.
2. The README included `python -m ber.confirm` in the normal training/evaluation reproduction block, encouraging repeated confirmation evaluation.

A subtler failure mode is selecting a window that partly overlaps a consumed range while extending into fresh anchors. Treating that as a “new” confirmation sample would mix known and unknown evaluation data. The guard rejects such windows outright.

## Interpretation

This does not improve the competition score directly. It protects the credibility of future score comparisons by making holdout consumption visible and deliberate.

The two existing confirmation scores remain useful as historical one-time measurements, but neither range should be treated as untouched again. Routine swarm iteration should stay on development/calibration slices; a fresh confirmation window should be spent only for a deliberate promotion/final-selection decision.

## Risks

- The manifest is a repository convention, not a cryptographic lock. A determined caller can edit code or the manifest.
- Two isolated clones could theoretically consume the same fresh range concurrently before either manifest update is merged. Fresh confirmation use should therefore also be claimed on GitHub before execution and start from the latest main manifest.
- The full CatBoost/DuckDB confirmation path was not executed in this chat because doing so would itself be an unnecessary holdout reuse and this runtime lacks the full S2/S3 inventory. The guard logic is isolated and covered by unit tests.
- Auto-updating the manifest makes a successful fresh evaluation leave a dirty tracked file by design; that change must be committed immediately with the resulting report.

## Recommendation

**PROMOTE.**

This is a low-risk evaluation-safety change with no model-score behavior change. Merge after normal code review. Future agents should treat `reports/CONFIRMATION_FREEZE.json` as canonical holdout-consumption state.

## Follow-up tasks

1. Require a GitHub claim/checkpoint before anyone uses `--consume-new` on a fresh confirmation range.
2. If concurrent final-selection work becomes likely, move fresh-window reservation into a centrally serialized mechanism rather than relying only on merged Git state.
3. Keep I002 config/cache fingerprints aligned with the config/result hashes recorded by the confirmation manifest.
