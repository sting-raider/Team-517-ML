# I032 — Bound the INT003 local-to-public score gap without leaderboard tuning

## Hypothesis

The reported INT003 public score of **0.917** is far below the frozen labeled confirmation score of **0.950198**. Before treating that discrepancy as evidence for any specific model change, quantify what is arithmetically possible under country-mixture shift and what ordinary same-population sample variation could explain. The leaderboard value is used only as a post-hoc scalar diagnostic, never as a label or tuning target.

## Change

Added a deterministic, dependency-free forensic helper that:

- streams the complete supplied `test_source1.tsv` and verifies its country census;
- reads committed INT003 labeled metrics without accessing new labels or probabilities;
- derives exact mixture identities for France-vs-non-France counterfactuals;
- computes a conditional two-sample Hoeffding bound for the narrow same-population-sampling hypothesis;
- refuses to turn any counterfactual French score into a pseudo-label or estimate.

No retrieval, matcher, threshold, feature, candidate cap, or submission output is changed.

## Protocol

Inputs:

- complete supplied `test_source1.tsv`: **1,732,544** rows / **175,022,086 B** / SHA-256 `3d4a32c54c2ca9c53fd7c2be105bf26f708f94c4d2f88eb370972a195665c2f5`;
- committed `reports/int003_depth10_confirmation.json`;
- committed `reports/int003_depth10.json`;
- reported public leaderboard scalar **0.917**, as recorded in current coordination Issue #228.

No S2/S3 text, test labels, France labels/pseudo-labels, candidate probabilities, confirmation reuse beyond committed aggregates, model fitting, threshold search, or external entity data were used.

Reproduce:

```bash
python tools/experiments/i032_public_gap_bounds.py \
  --test-source1 /path/to/test_source1.tsv \
  --confirmation-json reports/int003_depth10_confirmation.json \
  --int003-json reports/int003_depth10.json \
  --public-score 0.917 \
  --output reports/i032_public_gap_bounds.json
python -m unittest tests.test_i032_public_gap_bounds -v
```

Local execution streamed the full Source-1 test file in **6.37 s**. Focused tests: **4/4 PASS**.

### Statistical boundary

Per-anchor F0.5 lies in `[0,1]`. For two independent random samples from one common score distribution, Hoeffding gives

`P(|mean_A - mean_B| >= d) <= 2 exp(-2 d^2 / (1/n_A + 1/n_B))`.

This is used only as a conditional sanity check. The public entity count and country composition are not disclosed in the repo, and the actual test population includes unseen France, so the common-distribution premise is not assumed to hold.

The committed `[0.005892, 0.009956]` bootstrap interval is **only for the paired v3-minus-v2 improvement**. It is not an absolute confidence interval for v3's 0.950198 macro score and is not misused as one here.

## Results

### 1. Full test Source-1 country census

| Country | Anchors | Test share |
|---|---:|---:|
| India | 809,986 | 46.7513% |
| US | 663,106 | 38.2735% |
| France | 259,452 | **14.9752%** |
| Total | 1,732,544 | 100% |

These counts exactly reproduce the committed INT003 unlabeled country audit.

### 2. The public gap is much larger than the spread among labeled INT003 slices

| Labeled slice | INT003 macro F0.5 | Difference vs reported 0.917 |
|---|---:|---:|
| Calibration, 4,389 anchors | 0.949121 | -0.032121 public-minus-local |
| Development holdout, 3,051 anchors | 0.944783 | -0.027783 |
| Frozen confirmation, 5,000 anchors | **0.950198** | **-0.033198** |

The three labeled slices span only about **0.00542** from lowest to highest, while the reported public score is **0.02778–0.03320** lower than all three.

Under the deliberately narrow hypothetical that confirmation and public entities are independent random samples from exactly the same score distribution, a public sample of at least **2,516 entities** would make a difference of 0.033198 have a two-sided Hoeffding upper bound `<= 0.05`. If both samples had 5,000 entities, the bound is **0.00809**. This does **not** establish a statistical test of the actual leaderboard because its sample size/composition are unknown and the populations need not match.

### 3. Known US/India test reweighting is not enough

Frozen confirmation country scores are:

- India: **0.932699**
- US: **0.962081**

Reweighting those two scores to the actual non-France test mixture gives **0.945925**. Thus the known increase in India's share versus the 5,000-anchor confirmation population accounts for only about **0.004274** of the confirmation-to-test expectation under transfer. The remaining difference from that reweighted non-France score to 0.917 is **0.028925**.

### 4. France-only degradation is arithmetically sufficient, but this is not a France score estimate

Using the full-test France share `w_F = 0.149752` and holding non-France at the test-reweighted confirmation score `s_NF = 0.945925`, solve:

`0.917 = w_F * s_F + (1 - w_F) * s_NF`.

The required French mean would be **0.752774**.

That is a counterfactual requirement, not an estimate. It is approximately 0.193 below the reweighted non-France value. If the displayed public score is rounded to the nearest 0.001, the corresponding required French score range is approximately **0.7494–0.7561**.

For comparison, if France merely matched the labeled India confirmation score of 0.932699, the full-test mixture would be **0.943944**, still far above 0.917. If France matched the reweighted non-France score, the mixture would be **0.945925**.

### 5. The unknown public country mixture matters materially

Assuming non-France remains at 0.945925, the French score required to produce 0.917 depends on France's unknown share of the public subset:

| Hypothetical France share in public set | Required France score |
|---:|---:|
| 3% | -0.0182, impossible |
| 5% | 0.3674 |
| 10% | 0.6567 |
| 15% | 0.7531 |
| 20% | 0.8013 |
| 25% | 0.8302 |
| 30% | 0.8495 |

With non-France fixed, France must make up at least about **3.06%** of the public set even if its mean score were zero. The repository does not establish the actual public-country composition, so no row in this table should be treated as the true case.

Conversely, at the actual full-test France share, if France averaged 0.80 then non-France would need to average **0.937607** to reach 0.917; if France averaged 0.90, non-France would need to fall to **0.919994**. Therefore the same aggregate score can arise from many combinations of France and non-France degradation.

## Error analysis

The result rules out one tempting story but not another:

- **Not supported:** “0.917 is just ordinary jitter around 0.950.” The observed gap is much larger than labeled-slice spread, and same-distribution random-sampling would require a surprisingly small public subset for Hoeffding not to flag the gap.
- **Mathematically possible, not proven:** France alone could create the full gap under a public mix close to the complete test mix, but only with a large performance drop.
- **Also possible:** a mixture of France degradation plus US/India test shift, retrieval failures, decision/calibration drift, or a public subset whose country/difficulty composition differs from the complete test inventory.

Current independent evidence makes France robustness worth prioritizing without turning leaderboard feedback into training signal: X011 reports unusual unlabeled French output cardinality, and active D017 is auditing cross-anchor ownership conflicts. X013 is separately testing same-country train-vs-test Source-1 shift. Those are appropriate diagnostics because they use supplied records rather than hidden leaderboard truth.

## Interpretation

The public-local discrepancy is a **distribution/generalization warning**, not a threshold-selection signal. A France-only explanation is arithmetically sufficient under the complete-test country proportions, but the aggregate 0.917 score cannot identify which country or pipeline stage is responsible.

The correct response is to prioritize diagnostics and changes justified by supplied-record evidence: France-safe language-agnostic retrieval/representation, ownership/conflict handling, and same-country train-test robustness. Do not move the 0.625 threshold, candidate cap, or other production settings merely to chase the public scalar.

## Risks

- The public score is user-reported and may be rounded.
- Public leaderboard entity count and country mixture are unknown here.
- Confirmation is a deterministic hash window intended to behave like a random sample, not a literal IID draw.
- France has no labels, so no French F0.5 is measured.
- Aggregate mixture algebra cannot localize retrieval versus matcher versus decision error.

## Recommendation

**FOLLOW-UP.** Preserve INT003 as the labeled baseline, do not leaderboard-tune, and prioritize active France/generalization diagnostics plus retrieval/ownership work. Any production change still needs supplied-label validation on the exact same anchors before promotion.

## Follow-up tasks

No new issue is needed from this forensic: active D017 (cross-anchor ownership), INT005 (learned retrieval), and X013 (same-country adversarial shift) already cover the highest-value evidence paths without duplicating work.
