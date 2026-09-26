# R025 — Red-team complementary character-retrieval fusion semantics

### Hypothesis

The coordinator's complementary character-retrieval experiment should be safe to hand to INT003/R024 only if candidate-fusion scores are independent of record IDs. Equal retrieval evidence must not receive different model-facing RRF weights because of `entity_id` ordering.

### Change

Audited `src/ber/retrieval_v3.py` on latest main and found both RRF channels used ordinal positions:

```sql
row_number() OVER(PARTITION BY anchor ORDER BY retrieval DESC, r.entity_id)
```

Those ordinal positions are inserted directly into `1/(60+rank)` and `0.5/(60+rank)`, so an entity-ID tie-break changes the fused retrieval score itself.

The branch replaces only those two RRF weight ranks with score-only dense ranks:

```sql
dense_rank() OVER(PARTITION BY anchor ORDER BY retrieval DESC)
```

A focused regression test guards this exact semantic boundary. No production default, blocker-v2 logic, matcher feature schema, threshold, or candidate cap was changed.

### Protocol

- Base: latest main at `f87b43dff37991a9ffa7163f37dc5b5ec0ce794d`.
- Branch: `agent/i/R025-char-fusion-redteam`.
- Code fix: `ceefd52d72ce96ce45d2fcd677769b1bdaf1cf23`.
- Regression test head: `6e4a0e6f34a81743153e72c739ed168446eeb443`.
- Source inspected: `src/ber/retrieval_v3.py`, the implementation that produced committed `reports/int001_retrieval.json`.
- Synthetic check: three semantic candidates with tied base scores and tied char scores; only the literal candidate IDs are permuted.
- No challenge labels, confirmation/frozen rows, leaderboard feedback, or external business data were used in the red-team.
- Full S2/S3 rerun was intentionally not claimed in this chat because those raw files exceed the connected Drive transfer ceiling and the active INT003/R024 workers own the full matched-pool rerun.

Synthetic reference execution in the available Python runtime completed successfully.

### Results

The old ordinal RRF is not invariant to entity-ID permutation.

For the synthetic case:

| Candidate | Ordinal RRF under ID map A | Ordinal RRF under ID map B | Dense-rank RRF |
|---|---:|---:|---:|
| x | 0.01639344 | 0.01587302 | 0.01639344 |
| y | 0.02432575 | 0.02459016 | 0.02459016 |
| z | 0.02393753 | 0.02419355 | 0.02459016 |

Only IDs changed; retrieval evidence did not. The ordinal implementation changed all three fused scores. The score-only dense-rank implementation was invariant.

This is the same class of failure that caused INT001's ordinal candidate-rank feature to be rejected: entity-ID ordering is entering a model-facing numeric signal.

The committed INT001-R retrieval aggregates remain useful as evidence that the character channel contains complementary matches, but the exact fixed-cap RRF metrics (`base160_char_rrf160` and `source160_char_rrf160`) must be rerun before promotion because their fused scores were produced with ID-dependent ordinal positions. No corrected oracle or macro F0.5 is claimed here.

### Error analysis

1. **RRF weight leakage — confirmed.** Entity IDs determine ordinal positions among tied retrieval scores; positions determine numeric RRF weights.
2. **Hard-cap tie ordering — residual risk.** `source_candidates`, `char_candidates`, and final fused selection still use `entity_id` as a deterministic tie-break at hard caps. This branch does not change those semantics because blocker-v2 uses the same style and changing candidate membership would broaden the experiment. Tie prevalence and boundary impact need a full-inventory audit.
3. **Truth leakage — not found in this path.** Character/source indexes and queries are built without ground-truth labels; truth is consumed in `evaluate_table` after candidate generation for metrics.
4. **Anchor/slice drift — guarded.** The original experiment asserts exactly 4,389 calibration anchors and exact reproduction of the base160 candidate-pair recall before evaluating new retrieval.
5. **Cap accounting — structurally bounded.** The RRF table applies `<=160` after fusion. The committed mean candidate counts below 160 are therefore plausible; this audit found no evidence of an accidental >160 RRF pool.
6. **Union metric semantics — informational only.** The untruncated union reports membership/oracle evidence and is not the fixed-cap candidate pool used for the RRF result.

### Interpretation

The character channel itself is not invalidated. What is invalidated is using the currently committed fixed-cap RRF numbers as promotion-grade evidence without rerunning after score-only ranking. Because tied retrieval scores are common by construction in sparse evidence systems but their actual frequency at the relevant boundaries is not available in this runtime, the magnitude of metric change is unknown.

The dense-rank fix is minimal and consistent with the already-selected INT002 matcher design, which deliberately changed its candidate rank feature to score-only dense rank after the same ID-order concern.

### Risks

- No full S2/S3 rerun was performed here, so the corrected pair recall/oracle delta is unknown.
- Hard-cap candidate membership can still depend on `entity_id` when scores remain exactly tied at a boundary; this requires separate prevalence measurement before claiming complete ID independence.
- A dense-rank RRF can assign the same rank to many tied candidates, changing RRF score spacing versus standard ordinal RRF. That is deliberate for leakage safety and must be evaluated empirically.
- Concurrent INT003/R024 branches may already have generated caches from the old ranking. Their cache/config provenance must force regeneration.

### Recommendation

**FOLLOW-UP.** Do not promote or train the next submission on the old ordinal-RRF candidate pool. Rerun base+char and source-aware+char retrieval with the score-only dense-rank patch, regenerate any dependent caches, then perform the already-claimed matcher-coupled evaluation on identical development anchors. Treat `reports/int001_retrieval.json` fixed-cap RRF metrics as pre-fix evidence only.

### Follow-up tasks

- INT003/R024: regenerate candidate pools after this patch and report corrected retrieval + matcher metrics.
- Add a full-inventory tie census for base/source/char/fused cap boundaries if time permits; quantify how often ID tie-breaking changes candidate membership.
