# F004 — Same-address / different-business hard-negative audit

## Hypothesis

Distinct Source-1 anchors sharing an exact normalized address form a concentrated precision-risk family. The family may be especially useful for hard-negative mining because the current blocker gives exact normalized-address matches strong retrieval evidence, while the matcher also sees address exactness.

## Change

Added `src/ber/address_collision_audit.py`, a deterministic bounded-memory audit that discards entity IDs before grouping and reports aggregate address-collision and name-confusability statistics. Added `tests/test_address_collision_audit.py` covering normalization plus mixed same-name/cross-name collision groups.

No retrieval, matcher, threshold, or scoring behavior was changed.

## Protocol

- Baseline repository: `main` at `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`.
- Data: complete Drive `train_source1.tsv`, **210,069,713 bytes**, **2,206,821 records**. No sample.
- Fields used: business name, business address, country. Entity IDs were dropped before grouping and were never predictive evidence.
- Normalization matched the repository's lowercase + accent-strip + Unicode letter/digit + collapsed-separator semantics for the empirical pass.
- Empirical execution streamed/chunked the full file, sorted normalized `(country,address,name)` triples, then made one group census pass plus one name-pair pass.
- Full census aggregation after sorting: **5.29 s**. Pair-confusability pass: **5.18 s**, peak RSS about **92 MB**. Preprocessing/sort wall time was not separately instrumented.
- The consolidated helper was regression-tested on a synthetic multi-country fixture:
  `PYTHONPATH=src python -m unittest discover -s tests -p 'test_address_collision_audit.py' -v`.
- Candidate cap / matcher threshold: N/A; this is a Source-1 forensic experiment, not an end-to-end score experiment.

The helper's Python NFD accent stripping can differ from DuckDB `strip_accents` on unusual non-decomposing characters. Sensitivity is tiny here: **554 / 2,206,821 (0.0251%)** raw addresses contain non-ASCII characters, and only **24 / 117,160 (0.0205%)** collision records belong to such rows under the empirical normalization. No business names in Source-1 contained non-ASCII characters.

## Baseline

No F0.5 delta is claimed because this task does not change the model and does not evaluate S2/S3 candidates. The correct comparison population is the complete Source-1 inventory itself.

Current model context remains unchanged: depth-10 CatBoost at cap 640, with previously recorded confirmation macro F0.5 0.928835. F004 does not re-use that confirmation set.

## Results

| Metric | All | India | US |
|---|---:|---:|---:|
| Source-1 records | 2,206,821 | 883,188 | 1,323,633 |
| Exact normalized-address collision groups | 40,511 | 15,367 | 25,144 |
| Records in collision groups | 117,160 | 42,709 | 74,451 |
| Collision-record rate | **5.3090%** | **4.8358%** | **5.6247%** |
| Within-address record pairs | 153,505 | 50,164 | 103,341 |
| Cross-normalized-name pairs | **153,505** | **50,164** | **103,341** |
| Same-normalized-name pairs | **0** | **0** | **0** |
| P50 / P90 / P99 / max group size | 2 / 5 / 8 / 14 | 2 / 5 / 7 / 13 | 2 / 5 / 8 / 14 |
| Cross-name pairs sharing >=1 name token | 20.90% | **38.75%** | 12.23% |
| Cross-name pairs with name-token Jaccard >0.25 | 8.28% | **24.88%** | 0.22% |
| Compact first-6 name prefix equal | 0.304% | **0.632%** | 0.144% |

Every exact normalized-address collision observed on Source-1 involved multiple normalized business names. Thus the full **153,505-pair** collision mass is a direct hard-negative-like family rather than simple exact-name duplication.

### Concentration by group size

Only **7.24%** of collision groups have at least 6 anchors, but they generate **39.29%** of all cross-name pair mass.

- All: 6+ groups = 7.24% of groups, 39.29% of pairs.
- India: 6+ groups = 4.84% of groups, 28.46% of pairs.
- US: 6+ groups = 8.71% of groups, 44.55% of pairs.

This strongly favors group-size-aware sampling over uniform pair sampling if this family is added to matcher training.

### India is structurally different

India has a lower raw collision-record rate than the US, but its colliding addresses and names are substantially more ambiguous:

- **65.05%** of Indian collision groups have 11+ address tokens vs **0.195%** in the US.
- **86.69%** have normalized address length 51+ characters vs **1.31%** in the US.
- **8.38%** of Indian collision groups contain no numeric token vs **0%** in the US.
- **38.75%** of Indian cross-name pairs share a business-name token vs **12.23%** in the US.
- **24.88%** of Indian pairs have token Jaccard >0.25 vs **0.22%** in the US.

So India's problem is not simply "more shared addresses." Its shared-address negatives are much more textually confusable.

## Error analysis

Four concrete mechanisms emerge:

1. **Shared address, unrelated name:** 79.10% of all hard pairs have zero business-name token overlap. Exact address evidence alone is unsafe.
2. **Shared address, partially similar name:** concentrated in India; nearly one quarter of Indian hard pairs exceed 0.25 name-token Jaccard. These are the most plausible matcher false-positive pressure points.
3. **Large shared-address clusters:** 6+ anchor groups are only 7.24% of groups but 39.29% of pair mass. Naive uniform anchor sampling underrepresents their combinatorial ambiguity.
4. **Long / digit-poor Indian addresses:** Indian collision groups are overwhelmingly long and often lack a numeric discriminator, weakening simple house-number conflict logic.

## Interpretation

The current blocker assigns exact normalized-address keys a large bonus, so an S2/S3 record at a shared commercial address can be surfaced strongly for multiple anchors. The matcher also has `address_exact`, address token overlap, and number-agreement features. F004 shows that exact-address agreement is common enough among distinct Source-1 anchors that it should not be treated as near-conclusive identity evidence.

The highest-value follow-up is **hard-negative mining / weighting for same-address competing anchors**, especially group-size-weighted examples and the Indian partial-name-overlap slice. A corpus-frequency feature for normalized address or address evidence would also be mechanistically justified, but should be evaluated end-to-end rather than hard-coded as a veto.

## Risks

- Source-1 collisions are a proxy for the hard-negative structure the matcher sees across S1->S2/S3; F004 does not prove identical rates in target sources.
- No end-to-end F0.5 gain is claimed.
- No France label is inferred.
- No external identity data was used.
- Exact empirical counts use the documented Python accent-strip fallback; the non-ASCII sensitivity is very small but not literally zero.
- Pairwise name-token overlap is an analysis diagnostic, not a trained feature claim.

## Recommendation

**FOLLOW-UP.** Use this family in M006-style hard-negative mining and test address-frequency / competing-anchor evidence on the fixed development benchmark. Prioritize the Indian partial-name-overlap subset and size-weighted shared-address clusters.

Do not add a hard "same address means non-match" rule: legitimate same-business records can share addresses, and this experiment only establishes that address exactness is not uniquely identifying.
