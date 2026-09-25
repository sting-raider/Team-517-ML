# R009aR — Red-team null Source-1 cardinality-prior result

**Issue:** #143  
**Target:** R009a / PR #129 @ `5b4ef5ab95a1580946253b1d566f2ecc86ecd6d2`  
**Recommendation:** **PROMOTE the negative finding for the tested cheap S1-only feature family; narrow the wording of the rejection.**

## Question

Could R009a's near-random result be a false null caused by label/feature misalignment, fold contamination, a broken target, or a metric bug?

## Scope

Static source/artifact audit only. Local Python/container execution is unavailable, so no raw-data rerun is claimed. No confirmation/frozen holdout was consumed.

## Findings

### PASS — target definition and full-label count independently reconcile

R009a defines high cardinality as `|T| >= 5`. D006a's independently produced full-label cardinality counts are:

- 5: 321,957
- 6: 164,868
- 7: 63,968
- 8: 18,680
- 9: 4,205
- 10: 534
- 11: 37

These sum exactly to **574,249**, matching R009a. The prevalence is 574,249 / 2,206,821 = **0.2602154864**, matching the report's 26.0215%.

### PASS — Source-1 / truth alignment fails closed

The helper:
1. rejects duplicate Source-1 IDs;
2. rejects duplicate truth anchor IDs;
3. maps cardinality by `source1_entity_id` onto Source-1 rows;
4. fails if any Source-1 anchor maps to missing truth;
5. requires Source-1 and truth row counts to match.

With unique IDs and equal row counts, a complete non-null mapping implies the anchor sets are identical. No positional join is used, so row ordering cannot silently scramble labels.

### PASS — fold construction matches repository fold517

The helper uses the same SHA-256 `fold517:<entity_id>` first-8-hex modulo-100 rule as the repository. Reported fold counts:

- fit 1,323,457
- early 330,681
- calibrate 331,219
- holdout 221,464

sum exactly to **2,206,821**. The primary model fits only `fit`; early/calibrate/holdout are prediction-only diagnostics.

### PASS — rank metrics do not contain an obvious false-null bug

The custom AUROC implementation is tie-aware via grouped Mann-Whitney wins. The average-precision implementation groups equal scores and integrates precision over recall increments at each score level. Focused tests cover perfect and all-tied cases. Candidate-budget targeting sorts only predicted scores and never reads labels during ranking.

The top-10% selection uses 22,146 / 221,464 = **9.999819%** of holdout, so the reported 9.9295% captured-positive recall is genuinely below its random budget share, not a rounding artifact.

### PASS — the null is supported by multiple independent diagnostics

The rejection does not rest on one threshold metric:

- primary classifier holdout AUROC **0.500302**
- primary AUPRC **0.258865** vs holdout prevalence **0.258931**
- top-10% high-cardinality recall **9.9295%**
- regression Spearman **0.005276**
- US/India slices both near random
- stronger 200-tree depth-8 classifier holdout AUROC **0.502641**
- raw-only model holdout AUROC **0.502776**

A feature/normalization quirk large enough to reverse the conclusion would have to survive the raw-only model and also explain the near-zero regression rank correlation.

### PASS with note — full-corpus frequency features are transductive but inference-safe

`name_freq` and `addr_freq` are computed over the complete labeled-training Source-1 inventory before fold separation. That means holdout covariates contribute to an unlabeled corpus-frequency feature.

This is **not label leakage** and is consistent with the competition setting if the corresponding frequency is computed from the complete available Source-1 inventory at inference time. It should be described as transductive corpus statistics, not purely fit-fold statistics.

Importantly, this choice cannot plausibly explain a false null by withholding information; it gives the model *more accurate* corpus-level frequency context.

### FOLLOW-UP — constant-probability calibration baseline uses evaluation prevalence

`binary_metrics()` constructs its constant baseline with `prevalence = y.mean()` on the same slice being scored. Thus the holdout Brier/log-loss comparator is the **best constant probability chosen with holdout labels**, not a deployable fit-set prior.

That makes the statement "model Brier/logloss is not better than a constant rate" valid as a descriptive best-constant comparison, but it should not be read as an out-of-sample calibration baseline. A deployment-faithful comparator would use fit prevalence.

This does **not** affect AUROC, AUPRC, top-budget lift, country slices, or Spearman, so it does not invalidate the rejection.

### FOLLOW-UP — rejection wording is broader than the tested representation

R009a strongly rejects the tested family of **cheap Source-1 shape/collision/frequency features** as an adaptive-cap prior. It does not prove that every possible Source-1-only representation is useless.

The experiment did not test, for example, richer token/character representations or learned text embeddings. Those may still encode chain/franchise or address-type structure correlated with multiplicity, although the raw/normalized frequency results make a large cheap signal look unlikely.

Therefore the safe conclusion is:

> Do not drive adaptive candidate budgets from the tested 24-feature Source-1 structural/collision prior.

The broader wording "Source-1-only cardinality prediction" should be read as shorthand, not a proof over all possible S1 representations.

## Verdict by risk class

| Risk | Verdict |
|---|---|
| Label alignment | PASS |
| Duplicate/missing anchor handling | PASS |
| Target definition | PASS; exact match to D006a |
| Fold construction | PASS |
| Train/holdout separation | PASS |
| ID as predictor | PASS |
| Country as predictor | PASS; evaluation-only |
| AUROC/AP implementation | PASS by source/tests |
| Top-budget lift semantics | PASS |
| Full-corpus frequency leakage | PASS as inference-safe transductive feature; document it |
| Constant calibration baseline | FOLLOW-UP wording; uses evaluation prevalence |
| Broad rejection of all conceivable S1-only models | TOO BROAD; narrow to tested feature family |
| Confirmation/frozen holdout reuse | PASS; none |
| End-to-end F0.5 claim | correctly NOT CLAIMED |

## Recommendation

**PROMOTE the negative finding** for the tested lightweight Source-1-only feature family. There is no static evidence of a false-null implementation bug, and the target/fold/population numbers independently reconcile.

For R009, spend the next empirical budget on **candidate-side** signals: actual blocker fanout/saturation, retrieval score distribution and gaps, channel/source balance, and cap-boundary pressure. Those are causally closer to "needs a wider candidate budget" than truth cardinality inferred from anchor text.

Before merge, tighten two pieces of wording:
1. call the Brier/log-loss comparator a slice-optimal constant baseline, not a deployable prior;
2. phrase the rejection as applying to the tested structural/collision representation rather than every possible S1-only model.
