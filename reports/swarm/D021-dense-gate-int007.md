# D021 — combine calibration-selected dense gate with INT007 blank recovery

**Issue:** #299  
**Branch:** `agent/d/D021-dense-gate-int007`  
**Base:** `integration/int005-learned-retrieval` / PR #268  
**Recommendation:** **BLOCKED / FOLLOW-UP**

## Hypothesis

D009a showed that a calibration-selected +0.5 extra dense-only logit penalty (equivalent to dense prior -2.5 at the fixed 0.95 threshold) reduces neural32 false positives, while INT007 recovers exact-name candidates whose provider address is blank when the Source-1 normalized name is unique within country. The combined rule may retain both gains, but the official metric is per-anchor macro F0.5 so the two measured deltas cannot be added arithmetically.

## Change

Added a direct composition diagnostic to `src/ber/capped_match.py` plus focused tests.

The combined evaluator applies, in order:

1. the already-selected D009a dense-only penalty (+0.5 logit penalty, fixed from calibration),
2. the already-selected INT007 recovery rule (`max_same_name_s1_anchors=1`),
3. recovery against the **post-gate** decision set.

That ordering matters. A dense-only pair selected by V5 can be removed by the gate and then re-added by INT007 if it is an exact-name/blank-address/unique-name candidate. Any evaluator that simply adds the two macro deltas ignores this interaction.

The report now records, per split, gate-removed true/false edges, recovered true/false edges, and the subset of gate removals re-added by INT007, plus normal score slices.

## Protocol

- Same frozen cap32 neural32 candidate pool as INT006/INT007.
- Same 4,389 calibration and 3,051 development-holdout anchors already consumed by PR #268.
- Dense gate fixed at the calibration-selected +0.5 penalty; no holdout retuning.
- INT007 fixed at Source-1 same-country normalized-name count <=1; no recovery retuning.
- No model training, new candidate generation, new confirmation/frozen holdout, leaderboard feedback, France labels/pseudo-labels, external identity data, or record-ID predictive features.
- Source artifact inspected: committed `reports/capped_match_evaluation.json` on PR #268.
- Project/Library search found no pair-level cap32 cache or private error artifact available to this chat.

## Existing independent evidence

| Split | V5 | D009a dense gate | Delta | INT007 | Delta | Invalid naive additive reference |
|---|---:|---:|---:|---:|---:|---:|
| Calibration | 0.9772376 | 0.9778440 | +0.0006064 | 0.9779415 | +0.0007039 | 0.9785479 |
| Holdout | 0.9707021 | 0.9714487 | +0.0007466 | 0.9720945 | +0.0013924 | 0.9728411 |

The last column is shown only to document the tempting but invalid arithmetic. It is **not** a measured combined score.

INT007 adds 51 TP / 9 FP on calibration and 44 TP / 3 FP on holdout relative to original V5. D009a improves singleton FPR from 1.5873% to 1.1905% on calibration and from 6.0302% to 5.0251% on holdout. INT007 alone leaves calibration singleton FPR at 1.5873% and raises holdout singleton FPR to 6.5327%.

Candidate membership is unchanged in all three committed variants. Pair recall and blocking oracle are exactly identical:

- calibration pair recall 0.9794448809, oracle 0.9939180974;
- holdout pair recall 0.9784843869, oracle 0.9928230370.

## Execution result

The composition semantics were executed with five focused synthetic tests in this runtime: **5/5 PASS**. The critical test confirms that an eligible dense-only pair removed by the gate is re-added by recovery, proving that direct composition is not equivalent to arithmetic addition of aggregate deltas.

Exact combined macro F0.5 is **not measurable from the committed aggregate JSON alone**. PR #268's evaluator keeps the required pair-level state only while running: `chosen_logits`, dense provenance, record-derived recovery eligibility, and per-anchor truth. The committed JSON contains separate aggregate score slices but not the pair/anchor membership needed to reconstruct their interaction.

The current chat has no authenticated Modal volume access, and Project/Library search exposed no cached cap32 NPZ / `private_error_examples.json` artifact. Therefore no exact combined macro, country slice, singleton FPR, or re-add count is claimed.

### Exact rerun gate

Run the existing CPU evaluation from this branch against the already-populated private PR #268 volume:

`modal run modal_capped_match.py --action evaluate`

No new neural inference is required if the existing dense/cross score caches remain present. The generated report will contain `dense_gate_plus_blank_unique_recovery` with direct calibration/holdout metrics and interaction counts. Promotion should require those direct numbers, not the naive additive reference above.

## Error analysis

The combined rule has three interaction classes:

1. **Independent recovery:** original V5 false negatives eligible for INT007 remain recovered after gating.
2. **Useful gate removal preserved:** dense-gate false positives that are not INT007-eligible remain removed.
3. **Gate removal undone:** a dense-gate removal that is INT007-eligible is re-added. If such edges are disproportionately false positives, INT007 erodes the gate's precision benefit; if they are true positives, recovery repairs an otherwise harmful gate removal.

The committed aggregates do not expose the size or truth mix of class 3, which is exactly why direct paired evaluation is required.

## Risks / red-team checks

- **Threshold leakage:** none added; penalty and recovery rule are fixed from prior calibration-selected decisions.
- **Candidate-cap mismatch:** none; combined logic never adds outside the frozen cap32 pool.
- **Stale-cache risk:** the rerun must use the exact PR #268 cap32 score/candidate cache and fail closed on candidate-recall/oracle drift.
- **Holdout reuse:** the holdout has been repeatedly inspected, so even a positive direct result remains a replication/integration signal, not fresh confirmation.
- **France:** no labels exist; this task makes no France accuracy claim.

## Recommendation

**BLOCKED / FOLLOW-UP.** The code path and interaction test are ready, but exact empirical promotion evidence requires the private cached cap32 artifacts. Do not rerun full test output or promote dense prior -2.5 on the basis of the invalid 0.9728411 additive reference.
