# I028 — INT003 v3 feature train/inference parity audit

## Scientific question

Does the promoted INT003 matcher compute its four new lexical/character retrieval-channel features with identical inference-safe semantics during training and full-test scoring, or is there a train/test mismatch that invalidates the v3 result?

A second integrity question emerged during the trace: does the published `baseline_v2_fused_pool` confirmation diagnostic truly hold the frozen v2 feature contract fixed while changing only the candidate pool?

## Scope and protocol

Audited latest-main source:

- `src/ber/v3.py`
- `src/ber/retrieval_v3.py`
- `src/ber/v2.py`
- `src/ber/predict.py`
- `modal_v3.py`
- `src/ber/features.py`

The four v3-only model features are:

1. `log_lexical_retrieval`
2. `log_character_retrieval`
3. `log_lexical_hits`
4. `log_character_hits`

No challenge holdout/confirmation labels, model probabilities, leaderboard feedback, France labels, or external entity data were consumed. Full S2/S3 raw files remain above this session's Drive download ceiling, so this is a source-contract + synthetic integrity audit rather than a new score experiment.

Focused regression check:

```bash
python -m unittest -v tests/test_i028_v3_compat.py
```

Result: **3/3 PASS** in 0.003 s in the available NumPy runtime.

## Production v3 source trace

### Training path

`ber.v3.materialize` delegates to the existing v2 materializer with:

- `candidate_fn=fused_candidates`
- `query_fn=v3.pair_query`
- `feature_names=V3_NAMES`
- `index_fn=build_char_index`

The v2 materializer builds full-train frequency tables, invokes that fused candidate function, executes the supplied v3 pair query, and sends all returned fields through the same `v2.compute_rows` assembly used by inference.

### Full-test inference path

For `feature_version == 3`, `ber.predict.predict`:

- checks the saved config's feature schema equals `V3_NAMES`
- builds the test lexical index and test frequency tables
- builds/reuses the test character index
- uses the same `fused_candidates`
- `score_batch` uses the same `v3.pair_query`
- `prepare_groups` sends the resulting rows through the same `v2.compute_rows`

There is no alternate inference formula or reorder for the four v3 fields.

**Finding: PASS. Production INT003 train/test feature assembly is structurally symmetric.**

## Channel semantics

`fused_candidates` keeps separate channel evidence for every candidate:

- lexical score/hits are stored as `base_retrieval` / `base_hits`
- character score/hits are stored as `char_retrieval` / `char_hits`
- candidates absent from a channel receive exactly zero for that channel
- duplicate candidates across channels are grouped once and retain each channel's maximum score/hit count

`v3.pair_query` then exposes:

```text
ln(1 + base_retrieval)
ln(1 + char_retrieval)
ln(1 + base_hits)
ln(1 + char_hits)
```

Thus a missing channel maps deterministically to zero in both train and inference.

Character keys are country-scoped via `hash(country, k)`, and the same index/query code is used for train and test. No labels enter the channel statistics.

**Finding: PASS.**

## Rank and ID dependence

The fused RRF contribution uses score-only tie geometry:

```sql
rank() over (partition by anchor order by retrieval desc)
+ (count(*) over (partition by anchor, retrieval) - 1) / 2
```

Equal-score candidates therefore receive the same average-rank weight. The model-facing fused candidate rank is also `dense_rank(... order by retrieval desc)`.

Entity ID appears only in the final hard-cap tie break that decides candidate membership. That separate membership issue is already owned by R026 and is not a model-facing v3 feature.

**Finding: PASS for model-facing feature evidence.**

## Integrity defect found: frozen-v2-on-fused-pool diagnostic

The production v3 model is valid, but the historical `baseline_v2_fused_pool` counterfactual in `modal_v3.confirm_model` was not feature-contract pure.

Before this patch it did:

```python
bp_fused = old.predict_proba(x[:, :len(V2_NAMES)])[:, 1]
```

The first 53 columns of a v3 feature matrix are almost the v2 schema, but one feature deliberately changed semantics:

- v2: `retrieval / greatest(1, top_retrieval)`
- v3: `retrieval / greatest(0.000001, top_retrieval)`

That v3 change is necessary because fused RRF scores are sub-unit. At rank 1, the maximum possible fused score is:

```text
1 / 61 + 0.5 / 61 = 0.0245901639
```

So for every v3 fused pool, the v2 denominator floor of 1 remains active. A true frozen-v2 feature contract would therefore feed the raw fused retrieval value (at most about 0.0246) into `relative_retrieval_score`. The v3 prefix instead normalizes the top candidate to 1.0.

Therefore the published `baseline_v2_fused_pool = 0.930872...` changes **both** candidate distribution and this feature's semantics. It cannot be used as a clean estimate of “frozen v2 model on v3 candidates” or to quantify retraining recovery.

### Patch

Added `src/ber/v3_compat.py::v2_prefix_from_v3`, which copies the v2 prefix and reconstructs `relative_retrieval_score` with the exact v2 denominator rule per anchor.

`modal_v3.confirm_model` now applies this compatibility transform before the frozen v2 model is scored on a fused pool.

Focused tests verify:

- sub-unit fused scores are restored to the v2 raw-score scale
- ordinary v2 groups with top retrieval > 1 preserve ratio semantics
- group/row misalignment fails loudly

**3/3 PASS.**

## What this invalidates, and what it does not

### Unaffected

The promoted INT003 result remains valid:

- v3 training uses v3 semantics
- v3 confirmation uses v3 semantics
- v3 full-test inference uses v3 semantics
- the same-anchor **v2 original lexical pool vs v3 fused pool** final score comparison uses each model's native feature path
- the confirmed v3 macro F0.5 of **0.95019849** and its +0.00791354 gain over v2 original-pool confirmation are not changed by this audit
- v3 retrieval oracle and pair-recall measurements are unaffected

### Requires correction / rerun

The single historical field `baseline_v2_fused_pool` must be treated as confounded until recomputed with the patched feature transform.

Consequently, the I026/I027 error-budget statement that frozen-v2-on-fused-pool retraining “recovered 0.019326 macro” is not supported by a pure frozen-v2 counterfactual. Its main current-v3 decomposition remains valid because it uses v3 actual score/oracle, and the v2→v3 original-pool comparison remains valid.

No replacement score is invented here because the private confirmation feature matrix/model are on the shared Modal volume and this runtime has neither Modal credentials nor downloadable S2/S3 inventories.

## Red-team conclusions

No production INT003 train/inference mismatch was found in:

- v3 feature ordering
- channel score/hit transforms
- missing-channel handling
- frequency-table invocation
- character-index construction
- country scope
- fused candidate generation
- model-facing rank/tie semantics
- saved-config schema validation

One **comparison-only** feature-contract defect was found and patched for future reruns.

## Risks and limitations

- DuckDB is unavailable in this local runtime, so production SQL execution was not repeated here.
- The shared Modal environment is not authenticated in this session, so the corrected frozen-v2 fused-pool score cannot be recomputed now.
- The Drive connector still rejects S2/S3 files above 256 MiB, preventing a local reconstruction of the full fused confirmation pool.
- R026's hard-cap ID tie-membership issue remains logically separate.
- Feature parity does not imply France robustness; frequency/format drift is handled by the X-series audits.

## Recommendation

**FOLLOW-UP.**

Keep **INT003 promoted**: its production train/inference feature contract passes this audit and its confirmed score is unaffected.

Merge the comparison fix, then rerun only the already-consumed confirmation diagnostic on the private artifacts to replace `baseline_v2_fused_pool`. Until then, withdraw the exact “0.019326 retraining recovery” interpretation from planning documents; do not discard the main I026 conclusion that current v3 within-candidate error exceeds retrieval loss, because that decomposition does not depend on the confounded diagnostic.
