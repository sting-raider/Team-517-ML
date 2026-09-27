# R032 — neural32 cap-widening retrieval headroom

## Question

Does widening the same INT005 ANN + INT003 v3 retrieval family beyond INT006's final cap32 recover enough **structural** blocking headroom to justify the extra pair-scoring cost?

This task uses only already-committed PR #268 aggregate retrieval sweeps. No new candidate generation, model inference, holdout tuning, confirmation use, leaderboard feedback, or France labels are involved.

## Protocol

Inputs from `integration/int005-learned-retrieval` at `fdff7866c4419f4fb645aa8d45a2a15696b8b729`:

- `reports/int005_capped_india.json`
- `reports/int005_capped_us.json`
- `reports/int005_capped_holdout_india.json`
- `reports/int005_holdout_us.json`
- `reports/capped_match_evaluation.json`

The exact existing anchor universes are preserved:

- calibration: 1,754 India + 2,635 US = 4,389 anchors;
- holdout: 1,212 India + 1,839 US = 3,051 anchors.

Country blocking-oracle macro F0.5 is combined by anchor count. Candidate pair recall is combined by committed truth-link counts, not by anchor count:

- calibration truth links: India 6,102; US 9,174;
- holdout truth links: India 4,088; US 6,416.

Two views are reported:

1. **fixed dense16** while only final cap changes;
2. **calibration-selected dense allocation within each cap**, then evaluated unchanged on holdout. This does not choose the final cap from holdout.

All compared variants use the same INT005 ANN + v3 retrieval family and the same examples.

## Fixed dense16: pure cap effect

| Final cap | Pair-cost multiple | Calibration oracle | Holdout pair recall | Holdout oracle | Holdout oracle delta vs cap32 |
|---:|---:|---:|---:|---:|---:|
| 32 | 1x | 0.993918 | 0.978484 | 0.992823 | — |
| 64 | 2x | 0.994890 | 0.981531 | 0.994083 | +0.001260 |
| 128 | 4x | 0.996122 | 0.985910 | 0.995341 | +0.002518 |
| 160 | 5x | 0.996186 | 0.986481 | 0.995492 | +0.002668 |

Fixed dense16 therefore saturates sharply after cap128: cap128→160 adds only about **+0.000151** holdout oracle while adding another 25% pair budget.

## Calibration-selected dense allocation inside each cap

The best calibration oracle within each cap chooses:

| Cap | Calibration-selected dense slots | Calibration oracle | Holdout pair recall | Holdout oracle | Oracle delta vs current cap32 | Pair-cost multiple |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 16 | 0.993918 | 0.978484 | 0.992823 | — | 1x |
| 64 | 32 | 0.995248 | 0.983054 | 0.994341 | +0.001518 | 2x |
| 128 | 64 | 0.996659 | 0.987148 | 0.995795 | +0.002972 | 4x |
| 160 | 64 | 0.997264 | 0.989052 | 0.996467 | +0.003644 | 5x |

The cap128 dense64 vs dense32 calibration oracle difference is only ~0.000017, so the exact dense allocation there should not be treated as a robust discovery. The broader conclusion is about cap headroom, not a claim that dense64 is uniquely optimal.

## Country slices

Current cap32/dense16 holdout oracle:

- India: **0.991419**
- US: **0.993748**

Calibration-selected cap64/dense32 holdout oracle:

- India: **0.992681** (+0.001261)
- US: **0.995435** (+0.001687)

Calibration-selected cap128/dense64 holdout oracle:

- India: **0.994970** (+0.003551)
- US: **0.996339** (+0.002591)

Calibration-selected cap160/dense64 holdout oracle:

- India: **0.995519** (+0.004100)
- US: **0.997091** (+0.003343)

India has more high-cap retrieval headroom than US, but it also remains the weaker structural slice after widening.

## Error-budget interpretation

INT006/V5 holdout matcher score is 0.970702 while the current cap32 blocking oracle is 0.992823.

- current structural retrieval deficit to perfect: **0.007177**;
- cap160/dense64 structural deficit: **0.003533**;
- cap160/dense64 therefore recovers about **50.8% of the current retrieval-only deficit**;
- but its +0.003644 oracle gain is only about **12.4% of V5's total 0.029298 gap to 1.0**.

This agrees with I036: retrieval is still material, especially for India, but matcher/decision error remains the larger end-to-end limitation.

The aspirational 0.998 target is also above this same-family oracle on both splits:

- calibration cap160/dense64 oracle: **0.997264**, short by ~0.000736;
- holdout cap160/dense64 oracle: **0.996467**, short by ~0.001533.

So **widening this retrieval family alone cannot make 0.998 reachable on these labeled slices, even with a perfect matcher over the candidate pool**.

## Cost / practicality

The committed candidate-count quantiles for these variants sit at the configured caps, so cap64/128/160 correspond approximately to 2x/4x/5x pair-scoring work relative to cap32. For the full V5 test output (55,384,406 candidate pairs at cap32), naive fully saturated scaling would be roughly 111M / 222M / 277M pairs respectively. Those are cost estimates, not regenerated test candidate counts.

More candidates can also create additional hard negatives. A blocking-oracle increase is an upper bound, **not** an end-to-end score guarantee; the cross-encoder/CatBoost decision stack would need an identical-fit/calibration A/B at the wider cap.

## Validation

Added `tools/experiments/r032_neural_cap_headroom.py` and focused tests.

Executed in this runtime:

- **3/3 tests PASS**
- weighted pair-recall aggregation by truth-link count;
- weighted macro-oracle aggregation by anchor count;
- per-cap calibration selection and deterministic smaller-dense tie-break;
- `py_compile` PASS.

No tiny gain is promoted as an end-to-end result. The cap128 dense allocation difference is explicitly treated as fragile.

## Recommendation

**FOLLOW-UP, with widening behind matcher/decision work in priority.**

If one wider matcher experiment is affordable, the minimal informative A/B is **cap64 with the calibration-selected dense32 allocation**, because it is the first nontrivial structural step and costs ~2x rather than 4–5x. Its untouched holdout oracle gain is +0.001518, so any end-to-end gain materially smaller than that would confirm that matcher/decision handling, not candidate availability, is the limiting factor.

Do not jump directly to cap128/160 solely from oracle numbers. The extra structural headroom is real, but expensive, diminishing, and still insufficient for a 0.998 oracle on holdout.
