# I024 — INT002 v2 feature train/inference parity audit

## Scientific question

Does the selected INT002 matcher compute its six v2 features with the same inference-safe semantics during training and test scoring, or is there a hidden split, label, or ID dependency that would invalidate the current model?

This audit is deliberately separate from X009. X009 measures France distribution shift in the new anchor-frequency features; I024 checks the **implementation contract** that produces those features.

## Scope and protocol

Source audited on the fresh I024 branch created from current `main`:

- `src/ber/v2.py`
- `src/ber/predict.py`
- `src/ber/blocking.py`
- committed INT002 feature/config report

The six v2 features are:

1. `log_anchor_name_frequency`
2. `log_anchor_address_frequency`
3. `log_target_name_frequency`
4. `log_target_address_frequency`
5. `log_candidate_score_rank`
6. `relative_retrieval_score`

No challenge confirmation/frozen holdout, candidate probabilities, leaderboard feedback, or external identity data was accessed. DuckDB is not installed in this runtime, so the production SQL itself was not executed here. Instead, the source contract was traced end to end and checked with a dependency-light independent reference implementation.

Focused reference checks:

```bash
python -m unittest -v tests/test_i024_v2_feature_reference.py
```

Result: **5/5 PASS**.

## Source trace

### 1. Train and test use the same feature constructor

Training materialization in `ber.v2.materialize`:

- builds the retrieval index on `train`
- calls `frequency_tables(c, 'train')`
- calls the same `pair_query('train', ...)`
- sends returned rows through `compute_rows`

Inference in `ber.predict.predict` for `feature_version == 2`:

- builds the retrieval index on `test`
- calls `frequency_tables(c, 'test')`
- `score_batch` calls the same `pair_query('test', ...)`
- sends returned rows through the same `compute_rows`

No alternate inference formula or reordered v2 schema exists. The saved model config is also checked against `V2_NAMES` before scoring.

**Finding: PASS.** Train/test semantics are structurally symmetric.

### 2. Frequency scope is explicit and inference-safe

`frequency_tables` groups by `country` and normalized field value:

- anchor side: `source=1`
- target side: `source>1`, intentionally pooling S2 and S3
- empty normalized values are excluded from the table
- missing lookups become frequency zero through `coalesce(..., 0)`
- the model receives `ln(1 + frequency)`

The target record's source is still separately available in the original 47-feature prefix, so pooling S2/S3 frequency is a design choice rather than accidental loss of the target-source feature.

The tables use the **complete unlabeled inventory of the current split**. Thus training features use full train inventory statistics and test inference uses full test inventory statistics. This is transductive corpus context, but it is symmetric and label-free: ground truth, candidate labels, and entity IDs do not enter the frequency counts.

**Finding: PASS for leakage/parity.** This does not prove distributional robustness; X009 is the correct follow-up for France.

### 3. Candidate rank is score-only and tie invariant

`pair_query` uses:

```sql
dense_rank() OVER(PARTITION BY anchor ORDER BY retrieval DESC)
```

No entity ID appears in the model-facing rank. Equal retrieval scores therefore receive equal rank.

The final output is ordered by `p.anchor, r.entity_id`, but that ordering only controls row order. It does not enter any v2 feature and does not change CatBoost's per-row prediction.

The separate blocker hard-cap candidate-membership dependence on entity-ID tie order is real and already owned by R026. I024 does not relabel that issue as a v2 feature defect.

**Finding: PASS.**

### 4. Relative retrieval score is well-defined for every real candidate

The feature is:

```sql
p.retrieval / greatest(1, p.top_retrieval)
```

Current blocker retrieval is a sum of one or more terms:

```
bonus + ln(10000001 / posting_frequency)
```

Eligible postings satisfy `frequency <= 1000`, bonuses are non-negative, and even a single zero-bonus hit contributes:

```
ln(10000001 / 1000) > 9.21
```

Therefore every nonempty candidate group has `top_retrieval > 1`; the denominator floor never clips a real blocker-v2 group. The top candidate(s) receive relative score exactly 1.0, and all others are in (0, 1].

**Finding: PASS.**

## Synthetic/reference checks

The independent reference implementation verifies:

- country-local anchor frequency
- S2+S3 pooling on target frequency
- empty normalized fields map to zero-frequency feature value
- dense ranks are invariant to candidate-ID permutation when scores tie
- identical train/test inventories yield identical six-feature semantics
- blocker-v2's minimum eligible single-hit score exceeds the relative-score denominator floor

All **5/5** checks pass.

## Red-team conclusions

No implementation defect was found in the selected INT002 v2 feature path.

Specifically, this audit found **no**:

- label-derived frequency statistic
- entity-ID-derived model-facing rank
- train/test formula mismatch
- source/country join mismatch
- empty-field asymmetry
- hidden clipping of real relative retrieval scores
- v2 schema mismatch between saved config and inference

One important distinction remains: full-inventory frequency statistics are intentionally transductive and may shift across countries/splits. That is not a parity bug. It is exactly the transfer-risk question being measured independently by X009.

## Relationship to nearby red teams

- INT001's ordinal rank was invalid because tied candidates acquired different model-facing ranks from entity-ID ordering. INT002 replaced it with score-only dense rank; I024 confirms the v2 path preserves that fix.
- R025 concerns ID dependence in character-RRF fusion weights, not INT002's current v2 pair features.
- R026 concerns ID dependence in **hard-cap membership** under tied retrieval scores. That affects which candidates reach the matcher, but is separate from the six v2 feature values once a candidate is present.
- X009 measures France shift of anchor-frequency values and remains necessary because implementation parity does not imply distributional robustness.

## Risks and limitations

- DuckDB 1.5.5 is unavailable in this runtime, so the SQL was statically audited rather than executed against DuckDB.
- No full S2/S3 raw files were available through the live Drive connector; target-frequency **distribution shift** is therefore not measured here.
- The independent helper is a reference implementation of the source contract, not a replacement production path.
- No F0.5 delta is claimed. This is an integrity result for the already-selected model.

## Recommendation

**PROMOTE** the current INT002 v2 feature semantics past this train/inference-parity integrity gate. No production patch is warranted from I024.

Continue X009 for France anchor-frequency shift, and treat R026's hard-cap tie membership as a separate retrieval-integrity risk. Any future modification of frequency scope, rank semantics, or candidate fusion must invalidate/rebuild v2 feature caches before comparison.
