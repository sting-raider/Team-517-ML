# R027R — red-team of number-conditioned character rescue

## Question

Is R027 / PR #226's reported number-conditioned character-retrieval gain trustworthy enough to promote, or is it confounded by candidate-cap ID ties, non-comparable model-facing retrieval evidence, leakage, or arithmetic inconsistencies?

## Scope and protocol

Tier-0/1 source-and-receipt audit only. I inspected PR #226 at head `543e0fdc33fb8c3d8b770017c68f17754709e23f` against current INT003 source and committed reports.

No new challenge rows, labels, confirmation/frozen windows, France pseudo-labels, external entity data, or leaderboard feedback were consumed. No score was recomputed in this chat because the local Python/container execution pool was unavailable.

Primary paths audited:
- `modal_r027.py`
- `src/ber/retrieval_r027.py`
- `src/ber/retrieval_v3.py`
- `src/ber/v3.py`
- `src/ber/predict.py`
- `src/ber/features.py`
- `reports/r027_retrieval_any.json`
- `reports/r027_retrieval.json`
- `reports/swarm/R027-number-character-gate.md`
- `reports/swarm/INT003-character-fusion.md`
- `reports/int003_depth10.json`
- R026 / PR #184 hard-cap tie audit

## What passes

### Exact baseline parity

R027 reproduces the selected INT003 calibration retrieval baseline exactly on the same 4,389 anchors:
- pair recall: **0.944357161560618**
- entity recall: **0.9443263656280335**
- all-matches-retrieved: **0.8438481991781485**
- blocker-oracle macro F0.5: **0.9804608439335135**
- India oracle: **0.9691962151346861**
- US oracle: **0.9879591964622207**
- mean candidates: **148.04921394395078**
- cap: **160**

These match the committed INT003 calibration receipts.

### Same population, inventory, and threshold

The R027 runner reconstructs the same deterministic 30k development population and the same `fold(i) == 'calibrate'` subset, asserts **4,389** anchors, and queries the complete training target inventory. The frozen matcher uses the already-selected INT003 model and unchanged threshold **0.625**.

### No truth injection into retrieval

Truth is loaded only after candidate construction for evaluation. The number gate is derived only from supplied normalized anchor/target address text, and name-character retrieval uses the existing country-scoped character index. I found no label-dependent candidate insertion or record-ID-derived numeric model feature.

### Receipt arithmetic is internally consistent

For the any-shared-number variant at fixed cap160:
- pair recall: **0.944357161560618 -> 0.9477611940298507**, delta **+0.0034040324692327**
- oracle macro F0.5: **0.9804608439335137 -> 0.9817163755231513**, delta **+0.0012555315896375**
- India oracle: **0.9691962151346861 -> 0.9718617621318838**, delta **+0.0026655469971977**
- US oracle: **0.9879591964622206 -> 0.9882761447407160**, delta **+0.0003169482784954**
- mean candidates: **148.04921394395078 -> 148.14057871952608**, delta **+0.09136477557530**

The uncapped union reaches oracle **0.9817534150765955**; enforcing cap160 gives **0.9817163755231513**, only **0.0000370395534442** lower, so most of the measured oracle rescue survives the fixed cap.

## Findings that block promotion

### 1. Hard-cap membership is still target-ID dependent

Both the current production retrieval and R027 use target entity ID to break equal-score hard-cap ties. R027 adds two additional ID-sensitive selection boundaries:

```sql
QUALIFY row_number() OVER(
  PARTITION BY h.anchor
  ORDER BY h.retrieval DESC,t.entity_id)<=32
```

and

```sql
QUALIFY row_number() OVER(
  PARTITION BY s.anchor
  ORDER BY s.retrieval DESC,t.entity_id)<=160
```

R026 / PR #184 already demonstrated synthetically that this pattern can change physical candidate membership under ID permutation. R027 does not measure boundary-tie prevalence or the amount of its incremental recall/oracle delta attributable to such ties.

This does **not** prove the measured gain is fake. It means the tiny gain is not yet ID-invariant evidence. The risk matters because the variant has p50/p90/p99/max candidate counts all at 160, so many anchors reach the hard boundary even though actual boundary-score tie prevalence remains unknown.

Required replication: score-only/tie-safe boundary accounting or explicit overflow-at-boundary diagnostics, then recompute the paired retrieval delta.

### 2. Frozen-matcher delta is not a clean retrieval-only comparison

INT003 was trained on a two-channel lexical + character fused pool. R027 adds a third retrieval vote. The frozen model therefore sees changed values in model-facing retrieval/provenance features including:
- `retrieval`
- `key_hits`
- `log_candidate_score_rank`
- `relative_retrieval_score`

The raw `char_retrieval` / `char_hits` values remain defensible as name-character evidence, but the global fusion score/rank distribution is no longer the training distribution.

Therefore **0.9491209588 -> 0.9495986030 (+0.0004776442)** is a useful exploratory diagnostic, not an isolated estimate of the end-to-end benefit after matched-pool retraining. Promotion requires retraining the matcher on the R027 candidate semantics and evaluating an unchanged non-calibration slice.

This is consistent with INT003's own evidence that changing candidate pools without matched retraining can materially change model behavior.

### 3. The tiny matcher gain lacks paired robustness evidence

R027 evaluates the frozen matcher on the same 4,389 calibration anchors used throughout retrieval development. It does not provide:
- anchor-level improve/regress counts,
- paired bootstrap/uncertainty,
- target-source slices,
- or an independent development holdout result.

The gain is only **+0.0004776** and should be treated as fragile until replicated.

### 4. Singleton precision regresses

Frozen-v3 singleton false-positive rate changes:
- baseline: **0.0634920635 = 16 / 252**
- R027: **0.0674603175 = 17 / 252**

One additional singleton false positive costs exactly **1 / 4389 = 0.0002278423** macro score on this slice. Thus the positive aggregate matcher delta coexists with a singleton-precision regression and needs entity-level error accounting, especially because singleton precision is a known team priority.

### 5. Prototype composite-index cache provenance is unsafe

`build_number_char_index()` reuses `{split}_number_char_index` based only on table existence. It does not fingerprint source inventory, normalization, character-index semantics, number extraction, DuckDB/runtime semantics, or implementation source.

This is the same stale-cache class addressed for the INT003 character index by I030. It does **not** invalidate the committed R027 measurements because the measured `retrieval_gate` path performs the number filter directly over the existing character postings and does not use the prototype composite index. It **does** block promoting the prototype into production unchanged.

## Red-team verdict

**FOLLOW-UP; keep R027 on HOLD.**

The retrieval-oracle direction is credible enough to justify replication: baseline parity is exact, labels do not enter candidate construction, the fixed-cap arithmetic is consistent, and India receives the larger oracle gain. I found no evidence that the committed aggregate receipts were fabricated or evaluated on a mismatched anchor population.

However, the current evidence is not promotion-grade because:
1. incremental hard-cap membership can still depend on target IDs;
2. the +0.000478 frozen-matcher delta is calibration-only and is evaluated under shifted fusion/rank feature semantics;
3. singleton FPR regresses by one entity;
4. no paired uncertainty/error-diff accompanies the tiny matcher gain; and
5. the prototype composite index lacks provenance guards and runtime benchmarking.

## Required next gate

A promotion candidate should:
1. remove or explicitly account for boundary-tie ID dependence;
2. preserve cap160 and the exact same evaluation anchors;
3. retrain the current depth-10 matcher on the R027 candidate pool using the existing fit/early protocol;
4. calibrate only on the designated calibration fold;
5. report macro F0.5, India/US, singleton FPR, pair/entity/all-matches recall, oracle, candidate counts, paired entity deltas and uncertainty on an unchanged non-calibration slice;
6. add I030-style provenance to the composite index; and
7. benchmark index build/query runtime and storage.

No new confirmation window is warranted for the current exploratory effect size.
