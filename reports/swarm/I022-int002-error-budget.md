# I022 — Current INT002 confirmation error budget

**Recommendation: PROMOTE this decomposition as the current planning guardrail.** INT002 materially reduced matcher/decision error on the unchanged cap160 candidate pool, so retrieval now represents about 43% of the remaining macro-F0.5 gap to perfection rather than about 36% under the actual submission-v1 model on the identical anchors.

## Hypothesis

INT002's same-candidate matcher improvement should change the balance of the remaining error budget. If the matcher/decision gap shrank while the retrieval ceiling stayed fixed, research prioritization should be updated rather than continuing to use a pre-INT002 decomposition.

## Change

No model, threshold, retrieval, prediction, or production code changed. This is a Tier-0 arithmetic decomposition of the committed INT002 confirmation artifact.

## Protocol

- Source artifact: `reports/int002_depth10_confirmation.json`.
- Population: exactly 5,000 Source-1 anchors at hash positions 40,001:45,000.
- Candidate configuration: blocker v2, cap160, unchanged between the actual submitted-v1 baseline and INT002.
- INT002 threshold: 0.65, chosen before this confirmation evaluation on the calibration fold.
- Labels are used only through already-committed aggregate metrics.
- No new challenge rows or confirmation window were read for this analysis.
- No threshold, model, candidate, or retrieval parameter was tuned.
- No leaderboard feedback or external entity data was used.

For a slice with observed model score M and blocking oracle O:

- total gap to perfect = 1 - M
- retrieval-ceiling gap = 1 - O
- within-candidate matcher/decision gap = O - M

These components sum exactly to the total gap.

The singleton false-positive correction is a deliberately impossible upper bound: if every currently false-positive true singleton were identified perfectly and changed to the empty prediction while every other anchor stayed unchanged, each corrected singleton gains exactly 1/N in macro F0.5.

## Results

### Current INT002 error budget

| Slice | Entities | INT002 F0.5 | Blocking oracle | Total gap | Retrieval gap | Matcher/decision gap | Retrieval share | Matcher/decision share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| All | 5,000 | **0.940478** | 0.974176 | 0.059522 | 0.025824 | 0.033698 | **43.39%** | **56.61%** |
| India | 1,978 | **0.913639** | 0.961374 | 0.086361 | 0.038626 | 0.047735 | **44.73%** | **55.27%** |
| US | 3,022 | **0.958045** | 0.982555 | 0.041955 | 0.017445 | 0.024510 | **41.58%** | **58.42%** |

The remaining within-candidate matcher/decision gap is about **1.30x** the retrieval-ceiling gap overall. Both stages remain material; neither can plausibly be treated as cleanup work.

### How INT002 changed the budget

The actual submitted-v1 model on these same 5,000 anchors and the same cap160 candidates scored 0.927580. Because the candidate pool is identical, its retrieval gap is exactly the same 0.025824.

| Same anchors/candidates | Submitted-v1 | INT002 | Change |
|---|---:|---:|---:|
| Macro F0.5 | 0.927580 | **0.940478** | **+0.012899** |
| Total gap to 1.0 | 0.072420 | **0.059522** | -0.012899 |
| Retrieval gap | 0.025824 | 0.025824 | 0 |
| Matcher/decision gap | 0.046596 | **0.033698** | **-0.012899** |
| Retrieval share of remaining gap | 35.66% | **43.39%** | **+7.73 pp** |
| Matcher/decision share | 64.34% | **56.61%** | -7.73 pp |

INT002 therefore converted exactly 0.012899 of same-candidate matcher/decision headroom into score. Retrieval did not get worse; it became a larger fraction of the smaller residual error because the matcher improved.

This is the central planning result. The old conclusion that roughly two-thirds of the remaining loss is matcher/decision error is stale for INT002.

### Singleton false-positive upper bound

Committed INT002 singleton counts and FPRs imply integer false-positive counts of 16 overall, 14 in India, and 2 in the US.

| Slice | True singletons | Singleton FPR | False-positive singletons | Impossible perfect correction | Share of total gap | Share of matcher/decision gap |
|---|---:|---:|---:|---:|---:|---:|
| All | 275 | 5.818% | 16 | **+0.003200** | 5.38% | 9.50% |
| India | 113 | 12.389% | 14 | **+0.007078** | 8.20% | 14.83% |
| US | 162 | 1.235% | 2 | **+0.000662** | 1.58% | 2.70% |

Singleton precision remains a real India-specific opportunity, but it cannot explain most of the remaining error. Even a perfect oracle correction of every currently false-positive singleton would leave overall macro F0.5 at only about 0.943678 if no other predictions changed.

### India concentration of the remaining loss

India is 39.56% of these confirmation anchors but contributes:

- **57.40% of the total remaining macro-score gap**,
- **59.17% of the retrieval-ceiling gap**, and
- **56.04% of the within-candidate matcher/decision gap**.

The weakness is therefore not confined to one layer. Both retrieval and matching/decision are disproportionately costly in India.

Per-anchor gaps tell the same story:

- India retrieval gap: 0.038626 vs US 0.017445.
- India matcher/decision gap: 0.047735 vs US 0.024510.
- India total gap: 0.086361 vs US 0.041955.

### What would be required for 0.998

The current blocking oracle is 0.974176. No matcher or decoder operating only on this candidate pool can score above it.

To make 0.998 even theoretically reachable, the blocker oracle must increase by at least:

`0.998 - 0.9741757658 = 0.0238242342`

That would close **92.26% of the current retrieval shortfall to perfection**. This is only a necessary condition. The current matcher/decision gap is still 0.033698, so retrieval improvement alone cannot deliver 0.998 either.

## Interpretation

INT002 successfully attacked the larger old error component. That success changes what should happen next.

1. **Complementary retrieval now deserves more weight.** Retrieval is 43.39% of the remaining observed gap, up from 35.66% on the exact same anchors/candidates before INT002.
2. **Matcher/decision work is still slightly larger.** The current within-pool gap is 0.033698 versus 0.025824 retrieval gap. Retraining on a better retrieval pool is therefore preferable to treating retrieval as an isolated blocker-only exercise.
3. **India is the highest-value robustness slice in both stages.** More than half of both error components comes from the 39.56% India share of anchors.
4. **Singleton gating is useful but bounded.** Current singleton false positives account for at most 0.0032 overall under an oracle correction, with most of that opportunity in India.

This supports the next-step sequencing already suggested by retrieval evidence: introduce the candidate-efficient complementary character pool, then retrain the INT002-style matcher on that distribution rather than reusing the existing classifier unchanged.

## Risks and red-team checks

- The 40,001:45,000 confirmation window is already consumed. This report only reuses committed aggregates and must not justify threshold or model tuning on those rows.
- The decomposition assigns all oracle-to-model loss to "matcher/decision" jointly. Aggregate metrics cannot separate calibration, thresholding, feature representation, or ranking mistakes from one another.
- The retrieval oracle assumes perfect selection among retrieved candidates and therefore is not an attainable model score.
- The singleton correction is an oracle upper bound, not a proposed classifier result.
- France has no labels. None of these US/India confirmation slices estimates French performance.
- The comparison to submitted-v1 is valid because the INT002 confirmation artifact explicitly evaluates both models on the identical anchors and unchanged candidate pool. Historical cap640 confirmation numbers are deliberately excluded.
- No tiny sub-0.001 model claim is made here; all arithmetic identities are exact consequences of the committed aggregate metrics.

## Recommendation

**PROMOTE this error budget as the current research-prioritization baseline.**

For the next integration experiment:

- first retrain an INT002-style matched-pool model on the candidate-efficient base+character RRF160 retrieval pool identified by R024,
- measure whether the retrieval-oracle gain converts into end-to-end macro F0.5 on predeclared development data,
- report India and singleton behavior alongside the overall score,
- keep any new confirmation window untouched until a configuration has survived development and robustness gates.

Do not spend the next cycle solely on singleton gating or solely on widening the existing lexical cap. The current evidence says the valuable problem is joint: **better complementary retrieval plus a matcher trained for its harder candidate distribution**, with India as the critical labeled slice.
