# F013 — Source-1 anchor ambiguity and collision burden

## Hypothesis

Distinct Source-1 anchors may collapse under the current normalized name/address representation often enough to create a structural cross-anchor ownership problem. If so, collision membership might also correlate with true singleton/cardinality structure and justify anchor-level ambiguity priors.

## Change

No production matcher, retriever, threshold, or candidate budget was changed. This is a full-population forensic audit supporting active ownership/competition work (D017) and France robustness.

A deterministic helper was added at `tools/experiments/f013_s1_anchor_ambiguity.py`. It measures country-local collision groups for normalized name, normalized address, normalized name+address, and raw-exact name+address; then joins the complete supplied training truth to test whether field ambiguity is associated with singleton/cardinality/source-presence structure.

## Protocol

Inputs from the shared challenge Drive, complete rather than sampled:

- `train_source1.tsv`: **2,206,821** anchors (India 883,188; US 1,323,633)
- `train_ground_truth.tsv`: **2,206,821** truth rows
- `test_source1.tsv`: **1,732,544** anchors (France 259,452; India 809,986; US 663,106)

No Source-2/3 rows, confirmation/frozen holdouts, leaderboard feedback, external entity data, or French labels were used. IDs were used only to join supplied truth to Source-1, never as predictive evidence.

Latest-main production normalization is DuckDB `lower(strip_accents())`, Unicode non-letter/digit collapse, and trim. DuckDB is unavailable in this container, so the measured pass used Unicode NFD combining-mark removal, lowercase, Unicode letter/number punctuation collapse, and trim. This is a semantic mirror, not claimed byte-for-byte parity for every Unicode code point. Grouping used deterministic pandas uint64 hashes; equal strings necessarily hash together, so the zero-joint-collision result cannot be caused by hash collisions hiding equal values.

Because this environment terminates long individual commands near 45 seconds, the same complete populations were processed losslessly in persisted row partitions and then reunited for aggregation. No target or anchor sampling was substituted. Focused deterministic tests: **3/3 passed**.

## Results

This audit does not change candidates or predictions, so official macro F0.5 and candidate recall are **not applicable**. Current INT003 remains the score baseline (0.950198 confirmation macro F0.5); no delta is claimed.

### Joint name+address identity collisions are effectively absent

| Split / country | Anchors | Normalized joint collision groups | Affected anchors | Raw-exact joint groups | Normalization-induced groups |
|---|---:|---:|---:|---:|---:|
| Train India | 883,188 | 0 | 0 | 0 | 0 |
| Train US | 1,323,633 | 0 | 0 | 0 | 0 |
| Test India | 809,986 | 0 | 0 | 0 | 0 |
| Test US | 663,106 | 0 | 0 | 0 | 0 |
| Test France | 259,452 | **1** | **2 (0.00077%)** | 0 | **1** |

Across all **2.21M labeled train anchors**, not one pair shares both the normalized business name and normalized business address. Across **1.73M test anchors**, exactly two French anchors form one joint collision, and it is introduced by normalization rather than being raw-exact.

This rules out duplicate/identical Source-1 identity evidence as a material explanation for D017's observed target-to-multiple-anchor conflicts. Non-identical anchors can still compete for the same target, so target-side ownership/reverse retrieval remains a live mechanism.

### Field-level ambiguity is common

| Split / country | Name-ambiguous anchors | Address-ambiguous anchors | Address collision pairs | Address max group |
|---|---:|---:|---:|---:|
| Train India | 392,116 (44.398%) | 42,709 (4.836%) | 50,164 | 13 |
| Train US | 474,025 (35.812%) | 74,451 (5.625%) | 103,341 | 14 |
| Test India | 354,418 (43.756%) | 38,292 (4.727%) | 42,840 | 12 |
| Test US | 193,133 (29.126%) | 26,788 (4.040%) | 25,430 | 10 |
| Test France | 89,267 (34.406%) | **28,814 (11.106%)** | **63,463** | **101** |

France is the standout address slice: its affected-anchor rate is **2.35× India** and **2.75× US** on test. Collision-pair burden per anchor is **4.62× India** and **6.38× US**. The largest French normalized-address group has 101 anchors, versus 12 in India and 10 in US. No French accuracy conclusion follows from unlabeled data, but address-only evidence is plainly much less selective there.

Within labeled countries, India field ambiguity is fairly stable train→test (name -0.642 pp, address -0.108 pp), while US test is materially less collision-prone than train (name -6.687 pp, address -1.585 pp). That shift is relevant to any frequency/commonness calibration learned from training inventories.

### Anchor ambiguity is not a useful singleton/cardinality prior

| Country | Field | Singleton ambiguous | Singleton unambiguous | Delta | Mean cardinality delta |
|---|---|---:|---:|---:|---:|
| India | Name | 5.623% | 5.560% | +0.062 pp | -0.0016 |
| India | Address | 5.671% | 5.584% | +0.087 pp | -0.0168 |
| US | Name | 5.556% | 5.598% | **-0.042 pp** | -0.0107 |
| US | Address | 5.610% | 5.581% | +0.029 pp | -0.0057 |

Effects are tiny and not directionally stable. Both-source truth prevalence also moves by at most about 0.50 percentage points in these field-level comparisons. This is consistent with earlier null Source-1-only cardinality/singleton work: collision membership should not be used to force empty predictions or infer match count.

## Error analysis / interpretation

1. **Not an S1 dedup problem.** Joint normalized collisions are essentially zero. A deterministic winner-take-all rule among exact duplicate anchors would touch almost nothing.
2. **Name ambiguity is broad but weakly related to cardinality.** Common names create candidate competition, not a meaningful prior that the anchor is singleton or high-cardinality.
3. **France has unusual address ambiguity.** France's address collision structure is qualitatively heavier than both labeled countries. Country-local address commonness and competing-anchor evidence deserve explicit attention in France-safe inference.
4. **US train/test commonness shifts.** Frequency features should be interpreted as inventory-dependent evidence, not stable semantic probabilities.

## Risks

- Normalization parity is semantic rather than byte-for-byte because DuckDB `strip_accents` is unavailable here. The result should be replicated under production DuckDB before introducing any collision-derived production feature.
- France is unlabeled. Collision prevalence diagnoses selectivity/shift, not matching quality.
- Hash grouping is safe for detecting equality but is not a substitute for inspecting raw challenge rows; no row-level examples are committed.
- This audit uses Source-1 only. It cannot measure which target-side candidates actually generate cross-owner conflicts.

## Recommendation

**FOLLOW-UP.** Reject exact/joint S1 deduplication and S1 collision membership as singleton/cardinality gates. Feed the negative result into D017 so ownership logic stays target-side. Prioritize candidate-level competing-anchor/commonness evidence, and treat France address-only evidence conservatively because its S1 address collision burden is much higher than labeled-country test slices.

## Evidence-backed follow-ups

- D017 should stratify target multi-owner conflicts by S1 name/address collision commonness, not by exact joint duplicates.
- A future matcher/decision ablation can add candidate competition features such as number of S1 anchors sharing or nearly sharing the candidate's address/name evidence, evaluated on the normal development/calibration protocol before promotion.
- Replicate the France address-collision census under the exact DuckDB normalizer if production feature work depends on the absolute rates.
