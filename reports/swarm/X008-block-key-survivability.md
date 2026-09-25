# X008 — Source-1 blocker-key survivability and collision audit

**Issue:** #147  
**Pod:** X/R  
**Branch:** `agent/x/X008-block-key-survivability`  
**Recommendation:** **FOLLOW-UP**

## Hypothesis

Blocker-v2 may expose weaker or more collision-prone lexical evidence for India and unseen-France Source-1 anchors than for US anchors. The specific question is whether the actual blocker key families survive the hard `freq <= 1000` rule differently by country, rather than merely whether raw text formats differ.

## Change

No production blocker or matcher behavior changed.

This recovery run completed the full Source-1 census that the previous X008 agent could not execute. It mirrors the current `block_keys(n,a)` logic from `src/ber/blocking.py` for all eight families:

- exact name/address: `n:`, `a:`
- numeric composites: `h:`, `z:`, `d:`
- name token: `w:`
- address token: `u:`
- adjacent address-word pair: `v:`

The production query keeps exact/numeric `n/a/h/z` keys when their target posting frequency is <=1000, and keeps at most the four rarest eligible keys per non-exact family.

## Protocol

Complete supplied Source-1 files, no sampling:

- train Source-1: **2,206,821** anchors
  - US 1,323,633
  - India 883,188
- test Source-1: **1,732,544** anchors
  - US 663,106
  - India 809,986
  - France 259,452

The raw files were read from the shared Drive and processed locally in deterministic 200k-row shards. Each shard emitted de-duplicated blocker keys per anchor/family. Key document frequencies were then externally merged by split/country/family. A second complete pass measured anchor-level survival under a Source-1 proxy cutoff of `DF <= 1000`.

Because DuckDB is not installed in this chat runtime, normalization used the same Unicode NFD/combining-mark accent-fold semantic mirror used by X007/X002. The blocker-key construction itself mirrors the current production macro. X002 independently reproduced the full France accent-change rates with this mirror. This is sufficient for a forensic census, but any production behavior change still requires a DuckDB rerun.

Machine-readable aggregate: `reports/swarm/X008-block-key-survivability.json`.

### Integrity checks

- all five country/split row counts exactly match the repository audit;
- emitted family occurrences from the mapper equal the sums of merged per-key DFs;
- deterministic synthetic key cases covering stopwords, first/last numbers, duplicate tokens, adjacent pairs and accent folding pass;
- no exact `n/a/h/z` Source-1 proxy key exceeds DF 1000 in any evaluated country/split.

No labels, confirmation/frozen holdout, leaderboard feedback, external identity data, or record IDs as predictive evidence were used.

## Results

### 1. India has the clearest name-token survivability weakness

On test Source-1, the fraction of anchors retaining at least one proxy-eligible `w:` name-token key is:

| Country | eligible `w:` anchor rate | eligible `u:` address-token rate | eligible `v:` adjacent-pair rate | eligible `d:` numeric-address rate |
|---|---:|---:|---:|---:|
| US | **77.22%** | 94.39% | 96.32% | 100.00% |
| India | **56.75%** | 93.31% | 99.28% | 91.24% |
| France | **79.85%** | 97.38% | 99.85% | 99.57% |

India's name-token channel is therefore materially more often suppressed by the absolute-frequency rule than US or France in this S1 proxy. Train India is almost identical at **56.58%**, so this is not a test-only formatting shift.

This agrees mechanistically with the separate F007a finding that India names carry less rare-token redundancy. X008 extends that result across the complete production key family.

### 2. France has very common address vocabulary, but not anchor starvation

The fraction of emitted test key occurrences above the S1-proxy cutoff is:

| Country | `w:` | `u:` | `v:` | `d:` |
|---|---:|---:|---:|---:|
| US | 58.88% | 41.43% | 2.64% | 0.00% |
| India | 78.51% | 65.76% | 27.77% | 9.79% |
| France | 68.56% | **76.80%** | **49.91%** | **27.61%** |

France therefore has the strongest address-side high-frequency burden in the proxy, especially `u/v/d`. Its maximum test S1 DFs are 170,769 for `u:`, 101,521 for `v:`, and 4,423 for `d:`.

However, those common keys coexist with rarer alternatives. **77.42%** of French test anchors retain at least one eligible key in all four non-exact families, versus **70.60% US** and only **47.93% India**.

Only **0.00655%** of French test anchors emit non-exact keys but have all of them above the proxy cutoff. India is similarly tiny at **0.00617%**; US is effectively zero at **0.00015%**.

So the France problem is not generic “blocker keys disappear” under this S1 proxy. X002's measured loss of diacritic distinctions remains a more concrete France-specific representation concern.

### 3. Exact and numeric families are not suppressed in Source-1 proxy space

Maximum test S1 DF by exact/numeric family:

| Country | `n:` | `a:` | `h:` | `z:` |
|---|---:|---:|---:|---:|
| US | 123 | 10 | 40 | 160 |
| India | 99 | 12 | 253 | 545 |
| France | 205 | 101 | 264 | 262 |

All are below 1000. Every test anchor has an eligible exact name and exact address key under this S1 proxy. This is **not** proof that production S2/S3 posting frequencies stay below 1000, but it rules out Source-1 exact-key crowding as the observed explanation.

### 4. India emits many keys but loses more of their useful diversity

Mean emitted / proxy-eligible / post-four-per-family selected key counts per test anchor:

| Country | emitted | proxy eligible | selected proxy |
|---|---:|---:|---:|
| US | 14.14 | 11.14 | 11.10 |
| India | **29.24** | **18.69** | 14.16 |
| France | 23.22 | 12.83 | 12.01 |

India is not key-starved in raw count. It emits roughly twice as many keys as US, mainly because addresses are longer/richer, but commonness plus the four-rarest-per-family rule collapses that large raw inventory to a selected count only modestly above US.

That suggests a retrieval-quality issue rather than a simple “add more token probes” issue. The strongest follow-up is IDF/BM25/commonness-aware scoring or better mixed evidence, not blindly increasing the number of same-family probes.

## Error analysis / interpretation

The hypothesis is **partially supported**.

- **India:** yes. Name-token survivability is distinctly weaker and common-token burden is high. This is consistent with the current India score deficit and supports active R005/R006/M001-style IDF/commonness work.
- **France:** address-side keys are highly repetitive, but rare-key redundancy is still broad enough that almost every anchor retains non-exact evidence. The S1 proxy does not support a generic France blocker-starvation story.
- **US:** acts as the cleaner lexical baseline, especially for adjacent-pair and numeric-address families.

The absolute `1000` cutoff means population size matters. France has fewer S1 anchors than US/India, so these proxy rates should not be normalized away; the production blocker also uses an absolute posting limit. But production frequency is computed on the **S2/S3 target inventory**, not Source-1. These numbers diagnose pressure and mechanisms, not candidate recall.

## Baseline / metric boundary

Current selected reference remains:

- confirmation macro F0.5: 0.928835
- US: 0.948339
- India: 0.900722
- cap-640 pair recall: 0.947246
- blocking oracle: 0.980951

X008 does **not** remeasure any of those metrics. Complete S2/S3 target files remain above the live Drive connector's raw-transfer ceiling, and France has no labels.

## Runtime

Summed shard CPU time:

- first map/DF pass: train 187.05 s, test 159.69 s
- second survival pass: train 131.30 s, test 115.46 s

Shards were executed in parallel, so these are CPU-time sums rather than claimed end-to-end wall time. External merge-sort wall time was not separately instrumented.

## Risks

- S1 DF is a proxy for target posting frequency, not the production S2/S3 frequency table.
- The NFD accent-fold mirror is not a byte-for-byte proof of DuckDB `strip_accents` on every Unicode code point.
- Country corpus sizes differ.
- No inference about French accuracy is possible without labels.
- No blocker change should be promoted from this census alone.

## Recommendation

**FOLLOW-UP.**

1. Prioritize India-aware IDF/commonness weighting and BM25-style name/address retrieval over simply adding more same-family token probes.
2. For France, retain the current folded view but pursue X002's parallel Unicode-preserving channel; X008 does not show broad key starvation.
3. When a full-target runtime is available, repeat the exact census on S2/S3 posting frequencies and then benchmark candidate recall/oracle on the established calibration anchors.
4. Do not raise or remove the `freq<=1000` cutoff solely from this S1 result. R023 already showed the cutoff's discontinuity; X008 shows that commonness is family/country dependent, not that a global relaxation is safe.
