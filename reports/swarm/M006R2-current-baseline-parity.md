# M006R2 — current-baseline candidate-pool parity audit

## Recommendation

**REJECT / SUPERSEDED** the original M006 Variant A hypothesis that the selected matcher is trained on cap-80 candidates while being deployed on cap-160 candidates.

The current selected INT003 matcher is materialized, fitted, and deployed on the same **fused cap-160 candidate-pool semantics**. The useful hard-negative question has therefore changed: future work should test weighting/mining *within the current cap-160 pool*, a larger/more diverse fit-anchor population, or retraining after a genuinely changed retriever. It should not repeat cap80→cap160 retraining as though that distribution mismatch still exists.

## Hypothesis audited

M006 was opened from M006a evidence that an earlier selected depth-10 CatBoost had been trained on cap-80 retrieved candidates while wider cap-160/640 evaluation exposed a much more negative-heavy tail. The intended first experiment was to regenerate fit/early rows at cap 160 and retrain the otherwise identical matcher.

This recovery asks a narrower prerequisite question against latest `main`: **does that premise still describe the current selected model after INT002 and INT003?**

## Protocol

Tier-0 source and committed-artifact audit only.

Inspected on latest `main`:

- `src/ber/v2.py`
- `src/ber/v3.py`
- `src/ber/retrieval_v3.py`
- `src/ber/predict.py`
- `modal_v2.py`
- `modal_v3.py`
- `reports/SUBMISSION_2.md`
- `reports/int002_depth10.json`
- `reports/int003_depth10.json`
- `reports/int003_retrieval.json`
- `reports/swarm/INT003-character-fusion.md`

No new challenge rows were read, no confirmation/frozen window was evaluated, no threshold was tuned, no model was retrained, and no leaderboard feedback was used.

## Evidence

### 1. INT002 already materializes cap-160 fit candidates

`ber.v2.materialize(..., cap=160, ...)` has a cap-160 default. For every fit/early/evaluation anchor batch it calls the candidate function with that cap, allocates one feature row per returned candidate, and persists all rows.

`modal_v2.make_features()` calls this materializer without a cap override, so the default 160 applies.

The committed INT002 receipt confirms:

- fit anchors: **108,115**
- fitted candidate pairs: **15,431,847**
- candidate cap: **160**

Thus the current v2-generation training path is not the historical cap-80 training distribution described by M006a.

### 2. Training consumes every fitted candidate row

`ber.v2.train()` constructs the fit mask from candidate-row group IDs and calls CatBoost with `x[fit], y[fit]`. There is no negative subsampling step.

The only row weighting is inverse candidate count per anchor, normalized to mean one. Therefore lower-ranked false candidates that are present in the cap-160 fit pool are already seen by the model.

### 3. INT003 inherits cap-160 materialization and swaps in the fused retriever

`ber.v3.materialize()` delegates to the same v2 materializer while supplying `fused_candidates` and the v3 pair query/schema. It does not override the cap, so training remains cap 160.

`fused_candidates(..., cap=160)` retrieves lexical top-`cap`, character top-64, reciprocal-rank fuses them, deduplicates, and finally applies the same hard cap.

The committed INT003 receipt confirms:

- fit anchors: **108,115**
- fitted candidate pairs: **16,043,969**
- candidate cap: **160**

Relative to INT002, INT003 fits **612,122 more candidate rows**, a **3.9666%** increase, because the fused retriever changes pool membership while keeping the same hard cap.

### 4. Deployment uses the same fused cap-160 semantics

`ber.predict.predict()` loads `candidate_cap` from the saved model config when no explicit override is supplied. For feature version 3 it selects `fused_candidates`, calls it with that cap, scores the resulting table, and exports those considered candidates.

INT003's saved configuration reports cap 160. Therefore current training and test inference agree on the important distribution boundary being audited here: **fused retrieval, hard cap 160**.

### 5. Current measured candidate statistics are consistent with that path

On the fixed 4,389 calibration anchors, the committed INT003 retrieval gate reports:

| Candidate pool | Pair recall | Blocking-oracle macro F0.5 | Mean candidates | Max |
|---|---:|---:|---:|---:|
| lexical cap160 | 0.925308 | 0.973081 | 142.18 | 160 |
| fused cap160 | 0.944357 | 0.980461 | 148.05 | 160 |

The selected INT003 matcher scores 0.949121 on that calibration population. These values are context for the current cap-160 operating point, not new measurements from this audit.

## Result

The original M006 distribution-mismatch claim is **stale** for the current selected pipeline.

Historical question:

> Is a cap-80-trained matcher being asked to score a much wider cap-160 deployment pool?

Current answer:

> **No.** INT002 already fits on lexical cap160 candidates, and INT003 fits on the exact fused cap160 retriever family used at inference.

Running the original M006 Variant A now would largely reproduce the selected training regime instead of answering a new scientific question.

## Error analysis and remaining hard-negative questions

This audit does **not** show that hard-negative work is useless.

Three materially different hypotheses remain live:

1. **Within-cap160 hard-negative weighting/mining.** The model currently sees all fit candidates, but it may benefit from different weighting of high-scoring false candidates versus the many easy negatives.
2. **Larger or more diverse fit-anchor population.** Candidate-distribution parity does not establish that 108,115 fit anchors cover enough corruption/ambiguity modes.
3. **Retriever-conditioned retraining after a real candidate change.** INT003 itself demonstrates this principle: when the retrieval pool changes, retraining on the changed pool is necessary.

A cap640 rank>80 mining experiment is no longer the most faithful next step for the selected submission because deployment is capped at 160 and organizer guidance explicitly values smaller candidate sets. It becomes relevant only if a future promoted retriever actually widens the deployment pool or if rank>160 negatives are deliberately tested as regularization while evaluation remains fixed at cap160.

One additional caution: I028 established that the historical frozen-v2-on-fused diagnostic changed `relative_retrieval_score` semantics. That comparison should not be reused as evidence for or against hard-negative training. The current conclusion does not depend on it.

## Risks

- This is a source/receipt parity audit, not an empirical reweighting experiment.
- It proves candidate-boundary alignment at the cap/retriever-family level; it does not prove that every candidate has identical difficulty distribution across fit and test countries.
- France remains unlabeled, so no France matching-quality conclusion is possible.
- Future retrieval changes can immediately recreate a train/deployment mismatch unless feature materialization is regenerated from the exact promoted pool.

## Follow-up

Treat the original cap80→cap160 M006 Variant A as **superseded**.

If matcher work is scheduled next, use a newly registered experiment with one of these bounded questions:

- same fused-cap160 fit anchors and evaluation pool, alter only hard-negative weighting/mining and recalibrate on the designated calibration fold; or
- expand fit-anchor diversity while keeping the exact INT003 retrieval/features/cap fixed.

Report official macro F0.5, India/US, singleton FPR, candidate recall/oracle parity, threshold, training-row composition, and paired entity deltas. No confirmation/frozen window should be reused for tuning.
