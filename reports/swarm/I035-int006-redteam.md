# I035 — red-team INT006 neural32 integration and INT007 blank-address recovery

**Task:** #271  
**Target:** PR #268 at `fdff7866c4419f4fb645aa8d45a2a15696b8b729`  
**Branch:** `agent/i/I035-int006-redteam`  
**Recommendation:** **FOLLOW-UP** — V5/INT006 is credible as the strongest current development integration candidate, but PR #268 should not be treated as fully promotion-cleared until hard-cap tie dependence is quantified and V6 is replicated on an untouched gate.

## Scientific question

Are the large INT006/INT007 gains in PR #268 trustworthy under the repository's exact split, candidate-boundary, leakage, provenance, and output-contract requirements?

The red-team target is deliberately the exact integration head rather than a reconstruction.

## Capability and data-access check

The shared Drive dataset is accessible. The connector exposed the complete raw-file metadata and stream references for:

- `train_source1.tsv`: 210,069,713 bytes
- `train_ground_truth.tsv`: 127,015,583 bytes
- `test_source1.tsv`: 175,022,086 bytes
- `train_source2.tsv`: 489,301,488 bytes
- `train_source3.tsv`: 503,705,637 bytes
- `test_source2.tsv`: 509,456,422 bytes
- `test_source3.tsv`: 506,002,772 bytes

The three sub-256 MiB files were successfully fetched to streamed local file references. This chat's container/Python backend then returned a platform `ClientError` even for a trivial `ls`, so no new row-level recomputation is claimed. A default text fetch of the 175 MiB test Source-1 file also exceeded the tool's 64 MiB decoded-message ceiling. I therefore used the exact committed full-data receipts from PR #268 plus source-level path tracing; I did **not** substitute sampled S2/S3 data.

## Exact material audited

Code paths:

- `src/ber/dense_training.py`
- `src/ber/dense_retrieval.py`
- `src/ber/crossencoder.py`
- `src/ber/capped_match.py`
- `src/ber/predict_neural.py`
- `src/ber/recover_blank.py`
- `src/ber/retrieval_v3.py`
- `src/ber/v2.py`
- `src/ber/v3.py`
- `modal_dense.py`
- `modal_crossencoder.py`
- `modal_capped_match.py`
- `modal_neural_submission.py`
- `modal_app.py`
- `tools/package_final.py`

Receipts/reports:

- `reports/capped_match_evaluation.json`
- `reports/neural32_submission.json`
- `reports/blank_recovery_submission.json`
- INT005/D017, M017, INT006, and INT007 swarm reports

No confirmation/frozen-holdout labels were newly consumed by this audit and no leaderboard feedback was used.

## Finding 1 — INT006 training/evaluation separation passes the source audit

The learned retriever and cross-encoder both train from the INT003 **fit** anchors only.

`v2.select_anchors()` preserves the original 30k development population and adds only anchors at sample positions 50,001:200,000 whose deterministic fold is `fit`. `dense_training.prepare_partition()` then explicitly requires `m['fold'] == 'fit'`; calibration and holdout anchors never enter its label-derived positive/hard-negative training rows.

The cross-encoder reuses exactly those fit-only JSONL rows. It does not re-mine examples from calibration or holdout.

This audit found no path by which calibration/holdout truth labels enter encoder or cross-encoder fitting.

## Finding 2 — full-inventory ANN construction is label-independent

`dense_retrieval.encode_target_shard()` scans every supplied S2/S3 record satisfying split + country + hash-shard predicates. Labels are absent from the index-construction query.

The capped development pool is constructed as:

1. neural nearest-neighbor records from the complete same-country S2/S3 inventory;
2. then the highest-ranked surviving INT003 lexical/character candidates;
3. deduplicate;
4. hard-cap before matcher scoring.

Truth is consulted only after candidate construction for evaluation.

The production path mirrors this structure on `test`. Dense indexes are built from `source > 1` records and returned rowids are joined back to the same test table before serialization.

## Finding 3 — V5 model selection uses calibration only

`capped_match.evaluate_capped_match()` evaluates a bounded family:

- cross-encoder only;
- CatBoost + cross-encoder with dense-only priors -2, -1, 0, +1.

For every variant, its threshold is chosen on the 4,389-anchor calibration slice. The selected configuration is the calibration winner:

- dense-only prior: **-2**
- final threshold: **0.95**
- calibration macro F0.5: **0.9772376136**
- holdout macro F0.5: **0.9707021142**

The 3,051-anchor holdout is reported after that choice. I found no holdout-dependent branch in the V5 selection expression.

That makes the large V5 gain materially more credible than a post-hoc holdout-picked configuration, although the holdout itself has been reused by the wider project and is no longer a pristine estimate.

## Finding 4 — committed V5 arithmetic is internally consistent

On the exact 3,051-anchor holdout pool, the committed error budget says:

- truth links: **10,504**
- true links retrieved inside cap32: **10,278**
- retrieval misses: **226**
- predicted true links: **9,841**
- predicted false links: **73**
- true links retrieved but rejected by matcher: **437**

Thus `10,278 / 10,504 = 0.9784843869`, exactly matching the reported candidate-pair recall.

The same pool reports:

- V5 macro F0.5: **0.9707021142**
- blocking oracle macro F0.5: **0.9928230370**
- remaining matcher/decision gap to that oracle: **0.0221209228**

Country slices are also coherent with the report:

- India V5 holdout: **0.9683596536**
- US V5 holdout: **0.9722459218**
- India neural-only selected-pair precision: **236/271 = 87.08%**
- US neural-only selected-pair precision: **99/107 = 92.52%**

The lexical/character selected edges remain above 99.6% pair precision in both countries on this development slice.

The full test receipt contains:

- 1,732,544 Source-1 rows
- 55,384,406 candidate edges
- 5,743,094 V5 selected edges
- candidate SHA-256 `fa286e237b9bdd31905f901d2a1449771698249d4c1dfe45dcbfa38bf647c3ec`
- V5 matching SHA-256 `5a4aff5fcc37c74769ff3db1ebf2d35f85ab2258d80e5425e90ae616f1d7b33d`

That is about **31.97 candidates per test anchor**, consistent with a nearly saturated cap32 design.

## Finding 5 — prediction/candidate subset semantics pass

`predict_neural.score_partition()` writes `candidate_pairs.tsv` immediately after constructing `neural_candidates`, before either CatBoost or cross-encoder decisions are made.

Both matchers score only records from that frozen relation. Selected targets are appended only while iterating those exact records. The post-merge validator then verifies `predicted <= candidates` for every Source-1 row.

This satisfies the organizer contract that the submitted candidate file is the exact final candidate set fed to matching inference.

The 100-anchor France refactor probe reported byte-identical candidate and matching hashes before/after the explicit freeze refactor, supporting the claim that the refactor did not silently change membership on that probe.

## Finding 6 — hard-cap membership still depends on record IDs under ties

This is the main unresolved integrity issue.

The production neural32 path contains three ID-dependent boundary choices:

1. `neural_base32`: `ORDER BY retrieval DESC, t.entity_id`
2. final cap32: `ORDER BY priority, ranking DESC, t.entity_id`
3. dense Python ranking: sorting `(similarity, rowid)` in reverse, so rowid breaks exact similarity ties

The underlying `fused_candidates()` path also uses target `entity_id` to resolve hard-cap membership ties.

These IDs are **not model features** and do not change a surviving candidate's score. However they can change *which physical target survives* when permitted retrieval evidence is exactly tied at a hard boundary.

This is the same residual documented by R026, whose synthetic audit proved that ID permutation can change hard-cap membership. INT006 did not quantify boundary-tie prevalence or oracle sensitivity on its exact cap32 pool.

Because cap32 is much tighter than the historical cap160/640 settings, this needs a full-pool measurement before calling the retrieval path promotion-cleared. The present audit does **not** claim that tie dependence explains the +0.0259 V5 holdout gain; it only establishes that the dependence remains unmeasured.

## Finding 7 — the final merge skips the expensive target-ID membership scan

`modal_app.merge_score()` calls:

```python
validate(db, out, check_ids=False)
```

Accordingly, `reports/neural32_submission.json` truthfully records:

```json
"target_ids_checked": false
```

This is a validation-layer caveat, not evidence of invalid candidate IDs. Candidate rowids originate from test S2/S3 indexes and are joined back to `test` before output, while lexical indexes are likewise built from `source > 1`.

Still, before final archive submission, the exact candidate file with SHA `fa286e...` should receive the strongest feasible target-ID existence check, ideally on the existing Modal database where the data already reside.

## Finding 8 — V6's reported holdout score is not independent evidence

INT007's rule is:

- candidate already exists inside V5's frozen cap32 file;
- target normalized address is empty;
- normalized target name exactly equals normalized Source-1 name;
- that Source-1 normalized name occurs once within the same country.

The rule itself is simple and the max-count=1 variant improves calibration:

- V5 calibration: **0.9772376136**
- V6 calibration: **0.9779415358**
- delta: **+0.0007039221**

It also improves the reused holdout:

- V5 holdout: **0.9707021142**
- V6 holdout: **0.9720945236**
- delta: **+0.0013924095**
- added holdout edges: **44 TP / 3 FP**

However `capped_match.py` explicitly produces private error examples across both calibration **and holdout**, then evaluates many recovery/removal families and hyperparameters on both slices. The INT007 report itself says the rule family came from diagnosis of held-out errors.

Therefore the V6 holdout delta is post-inspection evidence, not an untouched replication. It must not be used as though V6 were independently validated on those 3,051 anchors.

There is also a precision tradeoff omitted from the headline: singleton false-positive rate rises from **6.03% to 6.53% overall** on holdout. India rises from **8.25% to 9.28%**. The official macro score still improves on that inspected slice, but this matters because singleton precision is a project priority.

The full test V6 receipt is mechanically consistent:

- changed Source-1 rows: 24,146
- added links: 25,143
- France: 5,798
- India: 8,071
- US: 11,274
- unchanged candidate SHA: `fa286e237b9bdd31905f901d2a1449771698249d4c1dfe45dcbfa38bf647c3ec`
- V6 matching SHA: `ab1b41964cdfbbccb4956c47d362d6c9b08cf7de73d67c3c8b66a963f61010e5`

## Finding 9 — model-license provenance passes this audit

The code pins both model revisions and checks the model-card license at training time.

Current public Hugging Face metadata independently confirms:

- `intfloat/multilingual-e5-small`: MIT, pinned revision prefix `614241f`
  - https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3
- `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`: Apache-2.0, pinned revision prefix `1427fd6`
  - https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1/tree/1427fd652930e4ba29e8149678df786c240d8825

Both are reported at about 117.6M parameters, far below the repository's 8B model ceiling.

## Rule-status dependency

V6 computes Source-1 name uniqueness from the complete unlabeled test split. That is a transductive test statistic, not external identity data.

Issue #270 / I034 is actively ingesting the organizer's 27 Sep query-form clarifications specifically covering unsupervised test-set statistics/self-training. This audit therefore does **not** independently label the V6 statistic permitted or prohibited; promotion should inherit I034's authoritative rules conclusion once checkpointed.

## What I did not find

- No record ID enters neural text serialization.
- No calibration/holdout labels enter dense or cross-encoder fitting.
- No truth-positive insertion into ANN results.
- No post-matcher candidate expansion.
- No S2/S3 sample substituted for the full-inventory retrieval claims.
- No evidence that V5's large gain is an arithmetic/reporting artifact.
- No evidence that the full test candidate/matching checksums disagree across the committed receipts.
- No France accuracy claim supported by labels; the PR correctly treats France output counts as unlabeled diagnostics.

## Recommendation

**FOLLOW-UP.**

### V5 / INT006

Treat V5 as the strongest current **development integration candidate** and worthy of final evaluation/submission comparison. The +0.025919 same-holdout gain over V3 is large, appears on both India and US, comes with a +0.0334 candidate-pair-recall jump despite a 5x smaller final candidate cap, and survived the major leakage/split/candidate-boundary checks above.

Before promotion as the fully audited final pipeline:

1. Quantify exact neural32 hard-boundary tie prevalence and the number of candidate memberships / true links / oracle score affected by ID tie-breaking on calibration and holdout, with country slices. Coordinate with existing R026 ownership rather than starting a competing implementation.
2. Run the strongest feasible target-ID validation against the exact candidate SHA on Modal before final archive packaging.
3. Keep France claims limited to unlabeled robustness/output diagnostics.

### V6 / INT007

**Replicate before promotion.** The rule is plausible and calibration-positive, but its holdout was inspected during rule-family discovery and the rule worsens singleton FPR on that same slice. Use a predeclared untouched gate if one remains, or otherwise clearly label V6 as calibration/post-hoc evidence rather than independent validation.

## Bottom line

I found no defect that explains away INT006's large development gain. The V5 result is substantially more credible after this audit.

I did find two reasons not to stamp the entire PR as promotion-complete: unmeasured ID-dependent cap32 tie membership, and V6's post-inspection holdout evidence. Those are bounded follow-ups, not a reason to discard the neural pipeline.
