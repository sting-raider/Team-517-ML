# I012 — Retrieval positive-injection / candidate-leakage red-team

**Issue:** #56  
**Branch:** `agent/i/I012-retrieval-leakage-audit`  
**Baseline audited:** current main, selected cap-640 reports  
**Recommendation:** FOLLOW-UP

## Hypothesis

The measured cap-640 pair recall / blocking-oracle ceiling could be optimistic if truth labels affect candidate membership, candidate rank, pruning, anchor selection, or oracle accounting.

## Scope

This was a Tier-0 source/artifact audit. I traced:

- `src/ber/blocking.py`
- `src/ber/retrieval_study.py`
- `src/ber/shortlist.py`
- `src/ber/experiment.py`
- `src/ber/wide_evaluate.py`
- `src/ber/candidate_budget.py`
- `src/ber/metrics.py`
- `src/ber/confirm.py`
- `src/ber/predict.py`
- `src/ber/validate.py`

and cross-checked `reports/retrieval_study.json`, `reports/wide_calibration.json`, `reports/submission_v1_confirmation.json`, `reports/tuning.json`, and `reports/RESULTS.md`.

No new challenge-data score was computed. This task deliberately does not consume another confirmation window.

## Result

### Direct label leakage / positive insertion: PASS

Candidate construction in `blocking.candidates()` depends on:

- anchor normalized name/address,
- anchor country,
- target posting keys from Source 2/3,
- posting frequency,
- fixed retrieval bonuses,
- deterministic target-ID tie-breaking.

It never reads `truth` or `edges`.

`experiment.materialize()` attaches labels only **after** candidate rows already exist. It loads each anchor's full truth set and sets `y[pos] = rid in meta[g]['truth']` for matcher training/evaluation. That labels the blocked pairs; it does not add missing positives.

### Anchor/fold selection: PASS

The development anchor universe is selected deterministically from Source-1 IDs; fit/early/calibrate/holdout assignment is a SHA256 bucket of the anchor ID. The retrieval study then selects only `fold == 'calibrate'` from the saved development metadata.

Truth is present in that metadata for scoring, but fold membership is not label-dependent. The repository data audit reports no missing truth anchors, so the truth join does not silently filter the selected 30k universe.

### Cap/rank semantics: PASS

For raw retrieval:

- `blocking.candidates(..., cap=640)` orders by `retrieval DESC, target entity_id`.
- `retrieval_study.py` recomputes rank with the same ordering.
- cap 80/160/320/640 is implemented as `rank <= cap`.

For the selected confirmation configuration, `candidate_cap=640` and `shortlist_cap=640`, so `predict.score_batch()` does not silently shrink groups already bounded to <=640. The exported `considered` set is therefore the candidate set used by the matcher.

### Oracle implementation: PASS

`metrics.evaluate()` computes:

- found positives = `truth ∩ candidates`;
- pair recall from the number of found positive links;
- entity recall over non-singleton truth entities;
- all-matches-retrieved over non-singletons;
- blocking oracle by scoring `found` as the prediction set.

That is the correct perfect-precision oracle under the candidate constraint: it includes every retrieved true match, no false positives, and predicts empty for true singletons.

Therefore the recorded confirmation values **pair recall 0.947246** and **blocking-oracle macro F0.5 0.980951** are not invalidated by any positive-injection or oracle-accounting issue found here.

### Full S2/S3 inventory across anchor folds: protocol caveat, not leakage

The retrieval index uses the complete unlabeled Source-2/3 inventory for every anchor fold. This is transductive with respect to the available search inventory, but it mirrors inference: all target records are available when resolving each Source-1 anchor. Held-out match labels do not enter retrieval.

### Reproducibility risk: retrieval study assumes a pre-existing index

`retrieval_study.py` calls `candidates()` directly. It does **not** call `build_index()` or assert the provenance/version/fingerprint of `train_freq` and `train_index`.

That means a future rerun can:
- fail if the index tables do not exist, or
- silently use an index produced by older blocker/data state if those tables remain in the DuckDB.

Even `build_index()` currently reuses an index from only the coarse integer `index_versions.version == 2`, so invoking it would not fully solve provenance.

This is consistent with the broader stale-cache risk independently found by I006 and belongs in the already-claimed I002 cache-fingerprint lane. It is not evidence that the historical report used leaked labels.

## Cross-check against I006

After claiming I012, I inspected the completed I006 audit and found substantial scope overlap. I006 already added a synthetic guard proving that a ground-truth link does not make an otherwise unretrievable target enter `blocking.candidates()`, and it identified the same broader stale-cache family.

I012 therefore serves as an independent narrow replication of the retrieval/oracle path rather than a new competing implementation. No duplicate guard was added.

## Risk assessment

- No direct candidate-label leakage found.
- No label-aware shortlist found.
- No candidate-cap/oracle mismatch found for selected v1.
- Record IDs are used only for deterministic selection/tie-breaking, not as matcher features.
- Historical cap-640 retrieval/oracle numbers remain valid working references.
- Future tiny-delta retrieval experiments remain exposed to stale-index provenance until I002 lands.

## Recommendation

**FOLLOW-UP.**

Keep the cap-640 confirmation pair recall **0.947246** and blocking-oracle macro F0.5 **0.980951** as the working baseline. Do not spend another agent cycle re-auditing positive insertion.

Prioritize:
1. I002 provenance/fingerprint enforcement for DB/index/candidate artifacts;
2. empirical retrieval channels (R002/R003/R005/R014) once full S2/S3 execution is available;
3. paired evaluation on exactly fixed candidate universes.

No production retrieval/scoring change is warranted from I012 itself.
