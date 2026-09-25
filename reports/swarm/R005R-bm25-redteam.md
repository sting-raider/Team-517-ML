# R005R — Red-team audit of BM25 name-retrieval experiment protocol

**Issue:** #79  
**Target:** R005 issue #46 / PR #66  
**Audited R005 head:** `0ba9a0b323dcd8d890801675916c57acbea74674`  
**Recommendation:** **FOLLOW-UP / DO NOT PROMOTE YET**

## Hypothesis

Before the P0 R005 BM25/IDF name retriever is promoted, an independent audit can detect protocol or runner defects that would invalidate a reported retrieval gain.

## Scope

This is a Tier-0 retrieval-integrity audit. It does not change the R005 retriever and consumes no new confirmation/frozen holdout.

Audited against current main:
- `src/ber/data.py`
- `src/ber/blocking.py`
- `src/ber/experiment.py`
- `src/ber/retrieval_study.py`
- `src/ber/metrics.py`
- `reports/retrieval_study.json`

Audited R005 files:
- `experiments/r005_bm25_name.py`
- `.github/workflows/r005-bm25-name.yml`

CI evidence:
- latest audited-head run: `36160380477`
- conclusion: **failure**
- artifact list: empty
- job-log download currently returns a GitHub/Azure blob 404, so the exact emitted failure line is unavailable.

## Audit results

| Audit class | Result | Evidence |
|---|---|---|
| Development anchor universe | **PASS** | R005 selects the first 30,000 S1 anchors by `md5('sample517:'||entity_id)`, matching main. |
| Calibration fold | **PASS** | R005 copies the exact `fold517:` SHA256 60/15/15/10 rule from `experiment.py` and evaluates only `calibrate`. |
| Baseline reference | **PASS** | R005 asserts pair recall `0.9458627913066248` and oracle `0.9811781091658961`, exactly matching main `retrieval_study.json:retrieval_640`. |
| Baseline blocker semantics | **PASS, subject to runner repair** | Block keys, bonuses, frequency cutoff 1000, rare-key top-4 rule, score, combined-source ranking and cap 640 mirror `blocking.py`. |
| Official retrieval metrics | **PASS** | Pair recall, entity recall, all-matches rate and oracle formula match `metrics.evaluate`. Singleton anchors receive oracle 1 when predicting the empty truth set. |
| Truth leakage / positive insertion | **PASS** | Truth tables are used for evaluation and source diagnostics only. BM25 and baseline candidates are generated from S1 text plus complete S2/S3 unlabeled inventories. |
| Confirmation / frozen holdout | **PASS** | No confirmation offsets or confirmation artifacts are touched. |
| Fixed-cap comparison | **PASS WITH CAVEAT** | R005 reports both raw baseline+BM25 union and an RRF re-pruned cap-640 set. Only the RRF result is a same-cap retrieval comparison; raw-union oracle delta must be interpreted together with added candidate count. |
| TSV parsing parity | **FAIL** | All six R005 `read_csv` SQL fragments double-escape the tab delimiter in Python source as `delim='\\t'`; main uses `delim='\t'`. |
| CI execution | **FAIL** | Latest run failed and produced no aggregate artifact. Therefore no BM25 gain exists yet. |
| Raw-data provenance | **WARN** | Download verifies Drive file ID + exact byte size, but not content hash. This is better than path-only provenance but still allows a same-size replacement/stale-input ambiguity. |
| Candidate-size reporting | **WARN** | Candidate total and p50/p90/p99/max are emitted, but mean candidate count is not explicit even though organizer guidance makes candidate-set size relevant. It is derivable as pairs/entities. |
| Runtime/memory | **UNKNOWN** | Instrumentation exists, but the failed run produced no result artifact. |

## Critical defect: double-escaped TSV delimiter

At R005 head `0ba9a0b3`, every `read_csv` occurrence contains two literal backslash characters before `t` in Python source:

```python
delim='\\t'
```

The production loader in `src/ber/data.py` contains one:

```python
delim='\t'
```

That difference matters because these strings are embedded inside Python SQL strings. In main, Python converts `\t` to an actual tab character before DuckDB receives the SQL. In R005, Python converts `\\t` to the two SQL characters backslash + `t`.

DuckDB documents ordinary SQL string literals separately from escape string literals: common backslash escapes such as `\t` require the `E'...'` form. DuckDB's CSV reader accepts delimiters up to four bytes, so a literal backslash+`t` can be treated as a two-byte delimiter rather than a tab. References:
- https://duckdb.org/docs/current/sql/data_types/literal_types
- https://duckdb.org/docs/stable/data/csv/overview

Therefore the current R005 script does **not** reproduce main's TSV parser and must be repaired before rerunning. The minimal fix is to match main's Python source spelling exactly at all six sites:

```python
delim='\t'
```

No BM25 parameter should change in the same repair commit.

The latest CI run also failed. Because its log blob is unavailable, this audit does **not** assert that the delimiter bug is proven to be the exact runtime error from run 36160380477. It is independently a deterministic parser-parity defect.

## Candidate-cap interpretation

R005 creates:
1. `baseline_candidates`: fixed cap 640.
2. `bm25_candidates`: up to 64 per source.
3. `union_candidates`: uncapped union of baseline + BM25.
4. `rrf_candidates`: re-ranked union capped back to 640.

This is scientifically useful, but the two deltas answer different questions:
- raw union: "how much recall can BM25 add if candidate budget grows?"
- RRF cap 640: "can BM25 improve retrieval quality at the existing budget?"

Only the second is evidence for a fixed-budget blocker replacement. The report should not present an uncapped-union oracle gain as a cap-640 gain.

## Leakage / contamination audit

No label-driven candidate generation was found.

- Ground truth is materialized before some retrieval SQL executes, but no truth table is joined into `query_keys`, `baseline_hits`, `bm25_target_tokens`, `bm25_hits`, union or RRF construction.
- `eval_edges` and `eval_edges_src` enter only metric/source-diagnostic queries.
- No record ID substring, prefix or hash is used as matching evidence. IDs are used for deterministic sample/fold selection and stable joins/tie-breaking.
- The calibration fold is repeatedly inspected development data, which is acceptable for this Tier-2 experiment but must not be described as untouched confirmation evidence.

## Provenance / reproducibility risk

R005 pins Python 3.12 and explicit versions for DuckDB, NumPy and gdown. The downloaded challenge files are checked against fixed Drive IDs and byte sizes.

However, content hashes are not recorded. Given the repo's existing stale-cache/provenance concerns, a successful rerun should emit SHA256 hashes for the four input files or consume the I002 provenance mechanism once integrated. This is a red-team recommendation, not evidence that the current files are wrong.

## Recommendation

**FOLLOW-UP. Do not promote R005 yet.**

Required before interpreting any BM25 result:

1. Repair the six tab delimiters only.
2. Rerun the exact same fixed BM25 configuration.
3. Require the baseline assertions to pass exactly before reading the BM25 deltas.
4. Report raw-union and fixed-cap RRF results separately.
5. Include mean candidate count and input content hashes in the final report if cheap.
6. If the runner still fails, move execution to the repository's authenticated/private data plane (e.g. the existing Modal volume/runner) instead of weakening the full-data protocol or silently sampling.

A successful fixed-cap result should still report pair/entity/all-matches recall, blocker oracle, country/source slices, candidate counts, runtime and memory on the identical 4,389 calibration anchors.

## Status

**FOLLOW-UP**. The scientific R005 hypothesis remains unmeasured at the audited head. The red-team audit found one deterministic execution/parity defect and no candidate-label leakage.
