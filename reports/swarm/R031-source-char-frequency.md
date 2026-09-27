# R031 — source-specific character-gram frequency for INT003 retrieval

## Hypothesis

INT003's character retriever currently pools Source 2 and Source 3 character-gram document frequencies before applying the DF<=2000 eligibility cutoff and inverse-frequency score. A gram that is common in one target source can therefore suppress or dilute evidence that is rare in the other source. The lexical blocker has already demonstrated the same structural failure mode for pooled S2/S3 posting frequencies (R020). Source-local character frequencies may recover additional true links, particularly in the weaker India slice, without increasing the final cap.

## Change

This branch adds an **opt-in** path only:

- `build_source_char_index()` hashes character postings by `(country, source, gram)`, so S2 and S3 have independent DF and eligibility.
- `source_char_candidates()` preserves the current DF cutoff (2000), minimum two-gram hit requirement, top-64 character candidate cap, and scoring constant.
- Query selection remains bounded to **six unique grams per c3/c4 family per anchor**, globally. It does not select six grams independently for each source, so the source-local variant cannot claim a gain merely by doubling the query-gram budget.
- `source_char_fused_candidates()` duplicates the selected INT003 lexical/character average-rank RRF formula but swaps only the character channel. Final cap remains 160.
- The selected production `build_char_index()`, `char_candidates()`, and `fused_candidates()` paths are unchanged.

The branch also adds `tools/experiments/r031_source_char_frequency.py`, which fail-closes unless it exactly reproduces the committed INT003 calibration pair recall and blocking oracle before evaluating the source-local variant.

## Protocol

Intended full-data gate:

- complete supplied train S2/S3 inventory;
- exact existing 30,000 development population and `fold517` calibration fold only: 4,389 anchors;
- no confirmation/frozen holdout;
- same lexical top160, character top64, average-rank RRF weights, and final cap160;
- baseline: current INT003 pooled-character fusion;
- changed: source-local-character fusion;
- required metrics: candidate pair recall, candidate entity recall, all-matches-retrieved rate, blocking-oracle macro F0.5, candidate count quantiles/mean, India/US slices, recovered/lost true pairs, runtime and memory.

Exact prepared-DB command:

```bash
PYTHONPATH=src python tools/experiments/r031_source_char_frequency.py \
  --db /path/to/full/prepared/data_v3.duckdb \
  --output reports/swarm/R031-source-char-frequency.json
```

If retrieval improves, the candidate distribution has changed and the matcher must be retrained on that exact pool before any end-to-end F0.5 promotion. The consumed INT003 confirmation window must not be reused for selection.

## Baseline

The following is **committed INT003 context, not a rerun in this chat**, from `reports/int003_retrieval.json` on the same 4,389 calibration anchors:

| Metric | INT003 pooled-character fusion |
|---|---:|
| Candidate pair recall | 0.9443571616 |
| Candidate entity recall | 0.9443263656 |
| All matches retrieved | 0.8438481992 |
| Blocking-oracle macro F0.5 | 0.9804608439 |
| India oracle | 0.9691962151 |
| US oracle | 0.9879591965 |
| Mean candidates | 148.0492 |
| p50 / p90 / p99 candidates | 160 / 160 / 160 |

The gate asserts pair recall `0.944357161560618` and oracle `0.9804608439335135` before interpreting any changed result.

## Result

### Source audit

Latest main confirms that production INT003 builds character postings with:

`hash(country, gram)` -> pooled S2+S3 frequency -> `DF<=2000`.

The new experimental path instead uses:

`hash(country, source, gram)` -> source-local frequency -> `DF<=2000`.

Static branch comparison also verifies the selected `build_char_index()` and `fused_candidates()` function bodies are unchanged. `char_candidates()` is semantically unchanged; the only textual difference is insertion spacing around the new functions.

### Deterministic mechanism

The suppression mechanism exists independently of challenge prevalence:

- S2 DF=2001, S3 DF=1: pooled DF=2002, so current INT003 drops the gram from **both** sources; source-local eligibility keeps the S3 occurrence.
- S2 DF=1500, S3 DF=600: pooled DF=2100, so current INT003 drops the gram even though it is individually eligible in both sources.
- When pooled DF remains eligible, source-local scoring cannot dilute a source's inverse-frequency weight because local DF <= pooled DF. For a 1-versus-1999 split, the rare source's score difference is exactly `ln(2000)` in favor of source-local weighting.

Five focused tests encode the index scope, fixed unique-gram budget, these cutoff/weight properties, and the requirement that selected INT003 still calls the pooled `char_candidates()` path.

### Execution status

Drive access was verified against the supplied shared folder. The files are present and downloadable in principle, but the live connector rejects:

- `train_source2.tsv`: 489,301,488 bytes
- `train_source3.tsv`: 503,705,637 bytes

because each exceeds the connector's 268,435,456-byte raw-transfer limit. Complete `train_source1.tsv` (210,069,713 bytes) did transfer and mount successfully, proving this is a per-file handoff limit rather than missing Drive authorization.

A direct raw S2 transfer attempt returned HTTP 413. The chat's Python and container backends also returned session-level `ClientError` before user code could execute, including on the mounted S1 file. Therefore:

- the focused tests are **authored but not claimed as executed**;
- the full S2/S3 gate is **not run**;
- no new pair recall, oracle, F0.5, India/US delta, runtime, or memory number is claimed;
- no target sample was substituted.

## Error analysis / interpretation

This is a real retrieval coupling mechanism, but its **challenge prevalence is unknown**. The source-local path can help only when useful grams have materially asymmetric S2/S3 frequencies or when pooled frequency pushes them over the 2000 cutoff. It can also hurt fixed-cap recall if newly admitted candidates displace stronger existing candidates.

The globally bounded six-gram selection controls one obvious confound. Remaining confounds are legitimate consequences of source-local evidence: which six grams are selected can change, their weights can increase, and previously pooled-ineligible grams can enter.

## Risks

- Full-target prevalence and fixed-cap displacement are unmeasured.
- A second character index increases storage/build cost; exact runtime/memory must be measured on the private full inventory.
- Hard-cap tie membership still inherits the known R026 entity-ID tie-break issue. No record ID becomes a numeric retrieval score or model feature in this branch.
- Any retrieval improvement requires matcher retraining on the changed pool before judging official end-to-end macro F0.5.
- France has no labels; no France accuracy claim is possible from this task.

## Recommendation

**FOLLOW-UP / BLOCKED EMPIRICAL GATE.**

Keep this branch as an executable full-inventory experiment, not a production retrieval change. Run the fixed-cap gate on the private Modal/shared-volume data plane. Promote only if source-local character DF improves same-slice oracle/recall at acceptable candidate/runtime cost, with particular attention to India; then retrain the matcher on the exact new pool and evaluate on a permitted, non-consumed selection split.

No external entity data, France labels, positive insertion, leaderboard tuning, or confirmation/frozen holdout was used.
