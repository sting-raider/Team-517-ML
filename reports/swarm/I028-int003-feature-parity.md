# I028 — INT003 v3 feature train/inference parity

## Hypothesis

INT003 adds four model-facing lexical/character channel features. If training, confirmation, and full-test inference materialize those values through different paths, or if target IDs can alter the values independently of permitted retrieval evidence, the selected v3 result could be invalid despite passing aggregate evaluation.

## Scope and protocol

This is a current-main source/integrity audit. No new challenge rows, labels, probabilities, confirmation/frozen windows, thresholds, models, or leaderboard feedback were inspected.

Audited paths:

- `src/ber/v3.py`
- `src/ber/retrieval_v3.py`
- `src/ber/v2.py`
- `src/ber/predict.py`
- `src/ber/shortlist.py`
- `modal_v3.py`
- committed INT003 model config / confirmation metadata

The four new model inputs are:

1. `log_lexical_retrieval`
2. `log_character_retrieval`
3. `log_lexical_hits`
4. `log_character_hits`

Two deterministic check sets were executed directly against the fetched current-main source and committed config: 13 structural path checks and 8 reference arithmetic/schema checks. All 21 passed. The local Python/container backend was unavailable with a platform ClientError during this audit, so no DuckDB execution is claimed.

## End-to-end parity trace

### Training / confirmation materialization

`ber.v3.materialize` delegates to the v2 materializer with:

- `candidate_fn=fused_candidates`
- `query_fn=v3.pair_query`
- `feature_names=V3_NAMES`
- `index_fn=build_char_index`

The v2 materializer builds the lexical index and split-local frequency tables, builds the character index, calls the supplied candidate function, and feeds the supplied pair query to the same `compute_rows` path used for all v2/v3 extra columns.

### Full-test inference

For `feature_version == 3`, `ber.predict.predict`:

- requires the saved `feature_names` to equal `V3_NAMES`
- builds/reuses the test lexical index
- builds split-local test frequency tables
- builds/reuses the test character index
- selects `fused_candidates` as the candidate function
- `score_batch` selects `v3.pair_query`

Therefore train and test use the same candidate constructor and the same SQL definition for all four new model inputs. The only intended difference is the split-local unlabeled inventory itself.

## Feature semantics

`fused_candidates` emits raw per-channel evidence:

- `base_retrieval`
- `char_retrieval`
- `base_hits`
- `char_hits`

A candidate absent from one channel receives zero for that channel before aggregation. `v3.pair_query` then exposes:

- `ln(1 + base_retrieval)`
- `ln(1 + char_retrieval)`
- `ln(1 + base_hits)`
- `ln(1 + char_hits)`

Missing-channel evidence therefore maps exactly to zero rather than NULL or an arbitrary sentinel.

The saved INT003 schema contains 57 features: the 53 v2 inputs followed by exactly these four fields in the same order produced by `pair_query`. `compute_rows` retains all columns from query position 9 onward, so the four fields are not truncated or reordered.

## ID-invariance

No target entity ID appears in the formula for any of the four new channel values.

Production fusion weights use retrieval-score-only tied ranking: equal channel retrieval scores receive the same average RRF position. A reference three-way tie produced the same RRF weight under target-ID permutation.

Target IDs still break ties at hard candidate caps in lexical, character, and final fused candidate membership. That is the already-documented R026 issue: a physical candidate may enter or leave at a tied boundary. Conditional on a candidate surviving, its four channel feature values do not change merely because its ID changes.

The second inference shortlist does not introduce a new discrepancy for current INT003: both `candidate_cap` and `shortlist_cap` are 160, and `shortlist_rows` returns the input unchanged whenever the group size is at or below the cap.

## Executed checks

### Structural source checks: 13/13 PASS

- v3 schema appends the four channel fields in the expected order
- query emits channel fields in matching order
- fusion table carries all four raw channel values
- production RRF weight rank is score-only
- final hard-cap ID tie-break is isolated to candidate membership
- training uses `fused_candidates`
- inference uses `fused_candidates`
- training uses `v3.pair_query`
- inference uses `v3.pair_query`
- inference enforces the saved feature schema
- training builds/reuses the character index
- inference builds/reuses the character index
- channel-feature expressions contain no target-ID term

### Reference arithmetic/schema checks: 8/8 PASS

- `log1p(0) == 0` for absent-channel evidence
- positive channel retrieval uses the expected `log1p` transform
- average tied RRF weight is invariant to target-ID permutation
- committed INT003 model has 57 features
- final four committed names exactly match the v3 schema
- candidate and shortlist caps are both 160
- shortlist is identity at or below the cap
- `compute_rows` retains all v3 extra columns

## Concrete integrity gap: character-index cache provenance

`build_char_index` currently treats table existence as sufficient proof that `<split>_char_index` is reusable. It does not store or verify:

- a character-index semantic version
- n-gram definition version
- DF cutoff/config fingerprint
- source-inventory fingerprint
- posting count/hash

`modal_v3.prepare_database` adds a database-level receipt with `version: 1` and the base database byte size, but that receipt is not derived from the character-index implementation/config and does not independently prove that both cached character indexes were built under the currently executing semantics.

This is a **stale-cache provenance risk**, not evidence that the selected INT003 artifact is wrong. The v3 training and test paths use the same prepared database, and the committed retrieval/confirmation results are internally consistent. Nothing in this audit demonstrates that the current train or test character index was stale.

However, a future code/config change can silently reuse an older character index because the cache compatibility check is weaker than the lexical index's explicit version mechanism.

A related legacy helper remains unsafe for future research: `retrieval_v3.experiment()` still contains the old entity-ID-ordered ordinal RRF implementation. Production INT003 does **not** use that helper; `modal_v3.retrieval_gate` calls the corrected `fused_candidates` path. R025 owns that historical fusion issue.

## Leakage / split checks

- Retrieval/fusion code does not read truth labels.
- Labels enter only after candidate generation when the materializer assigns `y` and when evaluation computes metrics.
- Country is used to scope retrieval keys but is not one of the four new channel inputs.
- Train feature construction uses train inventory; test inference uses test inventory. This is inference-safe split-local unlabeled corpus evidence, not label leakage.
- Target IDs are used for joins, deterministic export ordering, and documented hard-cap tie resolution, not as one of the four feature values.

## Risk assessment

The selected INT003 feature semantics pass this parity gate. No train/test mismatch or direct ID-derived value was found for the four new inputs.

The unresolved risk is artifact provenance: current cache receipts are not strong enough to prove character-index semantic compatibility after future code/config changes. This belongs to the same stale-cache failure family previously identified by I002/I006 and should be hardened before further retrieval revisions are compared.

## Recommendation

**FOLLOW-UP.**

Do not invalidate or roll back INT003 on feature-parity grounds. The four v3 channel features are train/inference consistent and ID-invariant conditional on candidate membership.

Before the next character-retrieval modification, add a fail-closed character-index fingerprint/version covering the n-gram definition, DF cutoff, source inventory identity, and implementation/schema version. Also avoid promotion-grade use of the legacy `retrieval_v3.experiment()` ordinal-RRF helper unless it is brought onto the production `fused_candidates` semantics.
