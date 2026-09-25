# F004R — Red-team same-address hard-negative audit

**Issue:** #137  
**Target:** F004 / PR #29 @ `4ea1c67a6f1075160391a8163ece84c7cc3b3f64`  
**Recommendation:** **FOLLOW-UP**; keep the qualitative finding, but do not call the committed counts exact production-normalized counts until a DuckDB-parity rescan is done.

## Question

Are F004's same-address collision counts and the downstream hard-negative interpretation sound enough to guide M006/address-frequency work?

## Scope

Static/source/artifact audit only. The local Python/container backends are unavailable in this chat, so no raw-data replication is claimed. No confirmation/frozen holdout was consumed.

Reviewed:

- F004 helper `src/ber/address_collision_audit.py`
- F004 focused tests
- F004 report / registry row
- production normalization in `src/ber/data.py`
- committed `reports/data_audit.json` population counts

## Findings

### PASS — population and country denominators are internally consistent

F004 reports 2,206,821 Source-1 rows, split 883,188 India + 1,323,633 US. Those exactly match the committed full-data audit. Its headline collision-record arithmetic is also internally consistent:

- 117,160 / 2,206,821 = **5.308994%**
- India: 42,709 / 883,188 = **4.835777%**
- US: 74,451 / 1,323,633 = **5.624746%**
- country collision groups sum to 40,511
- country collision records sum to 117,160
- country pair counts sum to 153,505

There is no denominator mismatch in those reported rates.

### PASS — grouping and unordered-pair accounting are logically correct

The helper externally sorts `(country, normalized_address, normalized_name)`, merges chunks in the same key order, and groups by `(country,address)`. For a group of size `n`, it uses `n(n-1)/2`; same-name pair mass is subtracted from total pair mass to obtain cross-name pairs. Name-similarity diagnostics are weighted by multiplicity `lc * rc`, so they represent record-pair mass rather than distinct-name-pair mass.

The synthetic test covers a mixed same-name/cross-name collision group and exercises the pair accounting. No obvious combinatorial double count was found.

### PASS — country isolation and ID leakage

Country is part of the F004 grouping key, consistent with blocker-v2's country-local hash keys. Entity IDs are not retained in the analysis tuple, so they cannot become predictive evidence in this audit.

### PASS — empty-address handling is harmless on this dataset

F004 excludes empty normalized addresses from collision groups. The committed full Source-1 data audit reports zero empty Source-1 addresses in both labeled countries, so this choice cannot affect F004's measured population.

### FOLLOW-UP — normalization is close, but not exact production parity

Production uses DuckDB:

```sql
trim(regexp_replace(lower(strip_accents(coalesce(s, ''))),
                    '[^\\p{L}\\p{N}]+', ' ', 'g'))
```

F004 instead uses Python `lower()`, Unicode NFD decomposition, removal of combining marks, and Unicode category filtering. The helper itself names this function `normalize_repo_like`, and the report correctly notes that NFD accent stripping can differ from DuckDB `strip_accents` on non-decomposing characters.

The report nevertheless says the empirical pass "matched the repository's ... semantics" and then argues sensitivity is tiny because only **24 / 117,160** currently colliding records contain non-ASCII address text. That 24-row statistic does **not** bound normalization sensitivity: **530 additional non-ASCII address rows (554 total minus 24 already-colliding)** currently sit outside Python-defined collision groups and are exactly the rows that could enter/merge groups under a different accent mapping.

What *is* safely bounded is the direct prevalence of potentially normalization-sensitive address rows:

- 554 / 2,206,821 = **0.025104%** of Source-1 rows.

That makes a large change in the *row collision rate* unlikely, but it does not establish exact pair-mass stability. A small number of remapped rows can join existing multi-row groups, and pair counts scale combinatorially.

Therefore the qualitative result "shared normalized addresses exist at nontrivial scale and form useful hard-negative candidates" is robustly motivated, but the exact 40,511 / 117,160 / 153,505 production-normalized counts should be labeled approximate until recomputed with the repository's DuckDB normalizer.

### FOLLOW-UP — reported runtime is not reproducible from the committed helper

The report gives "5.29 s aggregate census + 5.18 s pair-confusability pass after sorting." The committed helper performs both updates inside one `_update_group` traversal and contains no timing instrumentation, so those two stage times cannot be reproduced from the documented command. This does not affect the collision findings, but runtime provenance should be qualified or instrumented before using it for throughput comparisons.

## Red-team verdict by claim class

| Claim class | Verdict | Reason |
|---|---|---|
| Full Source-1 population size / country counts | PASS | exact agreement with committed full-data audit |
| Country-local grouping | PASS | matches blocker country partition |
| Empty-address handling | PASS | Source-1 has zero empty addresses |
| Pair combinatorics / multiplicity weighting | PASS | code and synthetic fixture are coherent |
| Entity-ID leakage | PASS | IDs discarded before grouping |
| Qualitative hard-negative mechanism | PASS | exact-address collisions among distinct anchors are mechanistically relevant |
| Exact production-normalized collision counts | FOLLOW-UP | Python NFD fallback is not literally DuckDB `strip_accents` |
| "24 rows bounds sensitivity" inference | FAIL as a bound | 530 non-ASCII rows outside current collision groups can move into/merge groups |
| Reported stage runtime reproducibility | FOLLOW-UP | final helper does not emit those stage timings |
| End-to-end F0.5 benefit | NOT CLAIMED | correctly deferred by F004 |

## Risk / impact

This does **not** invalidate the main F004 direction. Only 0.0251% of Source-1 addresses are non-ASCII, so the 5.3090% collision-row prevalence is unlikely to move materially. The issue is precision of provenance: hard-negative mining should be built from the production-normalized keys, not from an almost-equivalent Python surrogate when the exact DuckDB operation is available on the eventual training runner.

The pair-based concentration and India similarity percentages are more sensitive than the row rate because a remapped row can contribute multiple pair edges. Their exact production-normalized values remain unverified.

## Recommended correction / handoff

1. Re-run F004 once with DuckDB's exact `norm()` expression or add a direct parity census over all unique non-ASCII Source-1 addresses.
2. Replace "matched the repository's semantics" with "repository-like fallback" until parity is measured.
3. Do not use the 24 currently-colliding non-ASCII rows as the sensitivity bound; report all 554 potentially affected address rows.
4. Keep the hard-negative-mining recommendation, but generate the actual mining keys using production normalization.
5. Instrument end-to-end/preprocess/sort/aggregate timings if runtime is intended as evidence.

No production code change is warranted from this static review alone.
