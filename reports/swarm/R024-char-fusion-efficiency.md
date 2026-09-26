# R024 — Cap160 character-fusion efficiency triage

**Recommendation: PROMOTE base160_char_rrf160 as the first character-retrieval pool for expensive matched-pool retraining.** Keep source160_char_rrf160 as a secondary ablation/replication candidate, not the default.

## Hypothesis

Among the already-measured INT001 fixed-cap160 character-fusion variants, one may offer a materially better candidate-efficiency and India-robustness tradeoff for the next matcher retraining than the variant with the numerically highest aggregate retrieval oracle.

## Change

No production code or retrieval outputs were changed. This is a paired Tier-0 integration triage over the committed full-inventory retrieval experiment in reports/int001_retrieval.json.

The two fixed-cap candidates are:

- base160_char_rrf160: blocker-v2 base retrieval fused with the character channel by fixed-cap rank fusion.
- source160_char_rrf160: source-aware blocker retrieval fused with the same character channel by fixed-cap rank fusion.

For efficiency, both are also compared against the common deployed-style base160 reference. The source-aware fusion is additionally compared against its proper source160 parent.

## Protocol

- Evaluation population: exact same 4,389 calibration anchors used by INT001 retrieval.
- Search inventory: complete training S2/S3 inventory, as recorded by INT001.
- Candidate cap: 160.
- Labels: evaluation only; no positive injection.
- Confirmation/frozen windows: not accessed.
- Leaderboard feedback: not used.
- External identity data: not used.
- Source artifact: reports/int001_retrieval.json on main at the R024 branch point.
- Statistical limitation: committed artifact contains aggregate/slice metrics rather than per-anchor retrieval rows, so no paired bootstrap can be computed here. Deltas below 0.001 are therefore treated as unresolved unless supported by a stronger operational tradeoff.

All metrics below are retrieval-oracle quantities. They are **not end-to-end matcher scores**.

## Results

| Variant | Oracle macro F0.5 | Pair recall | Entity recall | All-matches retrieved | Mean candidates |
|---|---:|---:|---:|---:|---:|
| base160 | 0.973081 | 0.925308 | 0.925082 | 0.789944 | 142.18 |
| base160 + char RRF160 | **0.980810** | **0.945666** | **0.945547** | **0.847232** | **148.05** |
| source160 | 0.975083 | 0.928843 | 0.929223 | 0.800338 | 153.58 |
| source160 + char RRF160 | 0.981086 | 0.947041 | 0.947177 | 0.852550 | 155.50 |

Against the common base160 reference:

- base+char RRF: **+0.007729 oracle**, +0.020359 pair recall, +0.020464 entity recall, +0.057288 all-matches rate for **+5.87 mean candidates** (+4.13%).
- source-aware+char RRF: **+0.008006 oracle**, +0.021733 pair recall, +0.022095 entity recall, +0.062606 all-matches rate for **+13.32 mean candidates** (+9.37%).

Marginal quality per added mean candidate, relative to base160:

| Variant | Oracle gain / added candidate | Pair-recall gain / added candidate | All-matches gain / added candidate |
|---|---:|---:|---:|
| base+char RRF160 | **0.0013173** | **0.0034699** | **0.0097641** |
| source-aware+char RRF160 | 0.0006012 | 0.0016322 | 0.0047016 |

The base+char fusion is therefore about **2.19× more oracle-efficient per added candidate**, 2.13× more pair-recall-efficient, and 2.08× more all-matches-efficient versus the common base160 reference.

Directly comparing the two RRF160 variants:

- source-aware+char has only **+0.000277** aggregate oracle F0.5.
- It uses **+7.45 mean candidates** (155.50 vs 148.05), so base+char is 4.79% smaller by this mean-count measure.
- source-aware+char gains +0.001375 pair recall, +0.001631 entity recall, and +0.005318 all-matches rate.

The aggregate oracle difference is too small to treat as decisive without paired per-anchor evidence, especially because the organizer explicitly considers candidate-set size.

### Country slices

| Country | Metric | base+char RRF160 | source-aware+char RRF160 | source-aware minus base |
|---|---|---:|---:|---:|
| India | Oracle macro F0.5 | **0.969392** | 0.968586 | **-0.000807** |
| India | Pair recall | **0.918879** | 0.917240 | **-0.001639** |
| India | Entity recall | **0.919024** | 0.917986 | **-0.001038** |
| India | All-matches rate | **0.787787** | 0.787183 | **-0.000605** |
| US | Oracle macro F0.5 | 0.988409 | **0.989408** | +0.000998 |
| US | Pair recall | 0.963484 | **0.966863** | +0.003379 |
| US | Entity recall | 0.963214 | **0.966623** | +0.003408 |
| US | All-matches rate | 0.886830 | **0.896093** | +0.009263 |

The source-aware fusion's small aggregate advantage is US-driven. It moves in the wrong direction on India, which is already the weaker labeled country and a declared project priority. An equal-country average of oracle macro F0.5 is effectively tied: 0.978901 for base+char versus 0.978997 for source-aware+char, a difference of only 0.000096.

## Error analysis / interpretation

Three facts matter more than the raw aggregate ordering:

1. **The overall oracle gap is tiny.** +0.000277 is below the project's skepticism threshold for a repeatedly inspected calibration slice and lacks per-anchor paired uncertainty here.
2. **Candidate cost is not tiny.** The source-aware fusion carries 7.45 more candidates per anchor on average than base+char for that tiny oracle increment.
3. **The tradeoff is asymmetric by country.** Source-aware fusion improves US retrieval but slightly regresses every reported India retrieval metric relative to base+char.

The first expensive matcher retraining should therefore use base160_char_rrf160. It captures almost all of the measured fixed-cap character-retrieval oracle benefit, is materially more candidate-efficient, and does not trade away India performance for a sub-0.001 aggregate oracle edge.

This is intentionally not a claim that base+char will produce a higher end-to-end matcher score. A matcher trained on the new candidate distribution is still required.

## Risks

- Aggregate metrics do not reveal which anchors differ; no paired bootstrap/error-set analysis is possible from the committed JSON alone.
- Calibration anchors have been used repeatedly for development. This result is triage evidence, not an untouched estimate.
- France has no labels. Better India behavior does not prove better France behavior.
- The organizer candidate-size criterion is qualitative; no official scalar tradeoff between match score and candidate count is published.
- Character retrieval changes the hard-negative distribution. Reusing the current matcher without retraining would be invalid evidence.

## Recommendation

**PROMOTE to integration candidate:** train the next matched-pool CatBoost on base160_char_rrf160 first, using a fresh cache/config hash and the same score-only dense-rank discipline as INT002. Compare end-to-end macro F0.5, India/US, singleton FPR, candidate recall/oracle, and candidate counts on predeclared development data before any new confirmation use.

**REPLICATE second:** run source160_char_rrf160 only if compute budget permits a paired matcher comparison, because its aggregate retrieval advantage is too small and too US-concentrated to justify default priority.

## Follow-up

The next empirical integration should answer one question only: does retraining INT002-style matched-pool features on base160_char_rrf160 convert the +0.007729 retrieval-oracle gain into end-to-end macro F0.5 without worsening singleton precision or India?
