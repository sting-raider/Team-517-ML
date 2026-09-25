# M002 — Candidate rank and retriever-provenance features

**Issue:** #124  
**Pod:** M (matcher/features)  
**Branch:** `agent/m/M002-candidate-provenance-features`  
**Recommendation:** **FOLLOW-UP — empirical benchmark required before promotion**

## Hypothesis

The selected matcher collapses blocker evidence into only `retrieval`, `key_hits`, and target `source`. Two candidates can therefore reach the matcher with similar aggregate retrieval context even when one is supported by exact-name/address or number-aware keys and the other by weaker token evidence. Candidate rank also provides per-anchor relative context that the raw retrieval score does not encode directly.

Preserving rank and blocker-key-family provenance may improve precision, singleton handling, and India performance at a fixed candidate set.

## Current baseline

The current selected pipeline on the previously untouched 5,000-anchor confirmation set reports:

- macro F0.5: **0.928835**
- US: **0.948339**
- India: **0.900722**
- candidate pair recall at cap 640: **0.947246**
- blocking-oracle macro F0.5: **0.980951**
- singleton false-positive rate: **10.65% overall**, **13.51% India**

These are reference values only. This run did **not** consume confirmation/frozen labels and did not produce a new end-to-end score.

The selected matcher schema on main is 47 numeric inputs: 44 pair-text/number/missingness features plus `retrieval`, `key_hits`, and `source`.

## Static finding

The blocker already retains key kind while forming `query_keys`:

- `n:` exact compact name
- `a:` exact compact address
- `w:` name token
- `u:` address token
- `v:` adjacent address-token pair
- `h:` / `z:` name-prefix + first/last address-number evidence
- `d:` address-number + address-token evidence

However, baseline candidate aggregation discards that decomposition and stores only:

- summed retrieval score
- total key hit count

The matcher therefore cannot distinguish which evidence families produced those hits. It also does not receive blocker rank.

## Change

The branch adds an **opt-in** provenance path. Legacy behavior remains the default.

### Candidate table

`ber.blocking.candidates(..., provenance=True)` adds:

1. `candidate_rank`
2. `name_exact_hits`
3. `address_exact_hits`
4. `name_token_hits`
5. `address_token_hits`
6. `address_bigram_hits`
7. `name_number_hits`
8. `address_number_hits`
9. `min_key_freq`

The same blocker score and tie-break are used to assign `candidate_rank`. With `provenance=False`, the established blocker-v2 SQL path is retained.

### Matcher features

`src/ber/provenance.py` defines nine appended model inputs:

- raw `candidate_rank`
- the seven key-family hit counts
- `log1p(min_key_freq)`

This produces 56 features in provenance mode. IDs and labels are never inputs.

`ber.experiment.materialize(..., provenance=True)` writes the active feature schema to `feature_names.json` and fails closed if a provenance run attempts to reuse a legacy cache without schema metadata.

### Inference

`predict.py` now reads the model config's opt-in `provenance` flag. Provenance models:

- generate provenance candidate tables,
- append provenance features in the same order used at training,
- require the exact 56-feature schema.

Legacy model configs remain on the original 47-feature path.

## Protocol and validation status

This session inspected latest main, blocker-v2, feature materialization, selected inference, and the current tuning path before modifying code.

Focused synthetic regression tests were authored to check:

- provenance vs legacy candidate ID/count/retrieval/hit parity,
- provenance families partition total `key_hits`,
- blocker rank follows the established retrieval-desc/entity-ID ordering,
- cap-1 top candidate parity,
- provenance feature validation,
- inference feature assembly appends exactly nine fields without reordering the 47 legacy inputs.

**The tests were not executed.** After the complete Source-1 challenge files were transferred earlier in the session, every available Python/container invocation began failing at process start with a session-level `ClientError`, including a one-line shell command. There is no GitHub workflow-dispatch action available through the connected GitHub tool, and the repository has no discovered default unit-test workflow to invoke.

A static red-team pass did catch and fix one implementation bug before checkpointing: feature-importance reporting initially zipped a 56-element provenance model importance vector against the 47 legacy names, which would silently drop the nine new importances. It now uses the active schema.

## Required empirical benchmark

Do **not** promote M002 based on this implementation alone.

The decisive experiment must compare on the exact same development entities and candidate pool:

- baseline: current selected depth-10 CatBoost / 47 features
- variant: same training anchors, model hyperparameters, candidate cap, and candidate IDs, with the 9 provenance features appended
- fit/early/calibration partitions: unchanged fold517 protocol
- candidate set: assert exact anchor-target parity before fitting
- threshold: calibrate each model only on the designated calibration partition
- no confirmation/frozen holdout use during selection

Required outputs:

- official entity-level macro F0.5
- singleton false-positive rate
- US / India macro F0.5
- candidate pair recall and oracle, which should be identical if parity holds
- candidate counts/cap
- feature importance for all 56 fields
- runtime/memory overhead
- paired anchor-level score/error diff if available

The gain must survive the usual checks for stale caches, split mismatch, threshold leakage, cap mismatch, and accidental candidate-set change.

## Error analysis / expected mechanisms

The feature family is plausible for three concrete reasons, not because “more features” is a strategy:

1. **Evidence type is lost today.** Exact-name/address and number-aware evidence is qualitatively different from generic token overlap but currently collapses into the same two retrieval summaries.
2. **Rank is anchor-relative.** A retrieval value can have different meaning in dense versus sparse candidate pools; rank provides a cheap within-anchor context signal.
3. **Precision-heavy metric.** Provenance may be most useful in ambiguous/common-name cases and singleton false merges, where distinguishing strong from weak blocker support matters more than recovering additional candidates.

It can also fail. The new fields are strongly correlated with existing retrieval and pair similarities, and candidate rank is itself derived from retrieval. CatBoost may learn no stable incremental signal.

## Risks

- **No new measured F0.5.** Runtime failure prevented execution; no metric delta is claimed.
- **Tests authored, not run.** The branch requires executable review before merge.
- **Selected-baseline parity still must be demonstrated empirically.** Static code inspection is not a substitute for candidate-table set equality.
- **Rank/cap coupling.** Rank semantics depend on the retrieval pool and candidate cap; training and deployment must use compatible candidate generation.
- **Cache compatibility.** Provenance runs need fresh or schema-verified feature caches.
- **No retrieval gain claim.** M002 is a matcher-context experiment. Candidate recall/oracle should not change.
- **No record-ID leakage.** Entity IDs remain only identifiers/tie-break inputs already used by blocker ordering, not model predictors.

## Recommendation

**FOLLOW-UP / BLOCKED ON EXECUTION.**

The implementation is a useful handoff, but it is not safe to merge into the selected pipeline until the synthetic tests run and the exact same-slice depth-10 benchmark demonstrates a real macro-F0.5 or precision benefit.

If the measured delta is tiny, replicate it on another permitted development slice before promotion. If candidate parity fails, reject the score comparison until the cause is fixed.
