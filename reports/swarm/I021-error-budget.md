# I021 — Selected confirmation F0.5 error-budget decomposition

**Issue:** #169  
**Branch:** `agent/i/I021-error-budget`  
**Recommendation:** **PROMOTE** the error-budget framing into experiment prioritization. Retrieval remains a hard requirement for the 0.998 aspiration, but current matcher/decision headroom is materially larger than the current retrieval-ceiling loss.

## Hypothesis

The selected-v1 confirmation report already contains a same-slice model score and a same-slice blocking oracle. Their difference can separate the current official-metric loss into:

1. loss that cannot be repaired without changing candidate retrieval; and
2. loss that remains even if decisions were perfect inside the current candidate pool.

The same report also exposes singleton count and singleton false-positive rate, allowing the exact current-score value of an impossible-but-informative oracle singleton correction.

## Change

Added `src/ber/error_budget.py` and focused tests in `tests/test_error_budget.py`.

The helper consumes a committed evaluation JSON and fails if `macro_f0_5 > blocking_oracle_macro_f0_5`, singleton rates are invalid, or the reported singleton FPR does not correspond to an integer false-positive count. It optionally computes a clearly separated historical cap-expansion context from `wide_calibration.json`.

No model, retrieval, threshold, candidate set, or challenge record is changed.

## Protocol

Primary artifact: `reports/submission_v1_confirmation.json`.

This is the selected depth-10 model on the already-consumed **5,000-anchor confirmation window at offset 35,000**, with:

- candidate cap: **640**
- threshold: **0.625**
- blocker: **v2**
- overall macro F0.5: **0.9288349532**
- overall blocking oracle: **0.9809513535**

All decomposition terms below come from the **same anchors and same candidate pool**. Country rows are exact partitions of those 5,000 anchors: India 2,048; US 2,952.

The official row metric is `1.25*TP / (0.25*|truth| + |pred|)`, with true singleton score 1 only when predicted empty. Therefore every singleton with any false positive contributes exactly 0 rather than 1, making the singleton-oracle arithmetic exact.

Reproduction:

```bash
python -m ber.error_budget \
  --confirmation reports/submission_v1_confirmation.json \
  --wide-calibration reports/wide_calibration.json \
  --target 0.998 \
  --out reports/swarm/I021-error-budget.json
```

The helper arithmetic was independently executed in the local Python/container runtime; focused tests pass.

## Results

### 1. Same-slice error budget

| Slice | Current F0.5 | Blocking oracle | Gap to 1.0 | Retrieval-ceiling gap | Within-candidate model/decision gap |
|---|---:|---:|---:|---:|---:|
| All | 0.928835 | 0.980951 | **0.071165** | **0.019049** | **0.052116** |
| India | 0.900722 | 0.971389 | **0.099278** | **0.028611** | **0.070667** |
| US | 0.948339 | 0.987585 | **0.051661** | **0.012415** | **0.039246** |

For the full confirmation slice:

- **26.77%** of the gap to perfect is outside the current candidate pool and therefore retrieval-limited.
- **73.23%** of the gap to perfect remains between the current model/decision output and the perfect-within-current-candidates oracle.
- The within-candidate gap (**0.052116**) is **2.74×** the retrieval-ceiling gap (**0.019049**).

This does **not** mean retrieval is less important. The two interventions are not additive independent knobs. It means that the existing candidate pool still contains substantially more official-metric headroom than the selected matcher/decision layer currently captures.

### 2. The 0.998 aspiration still requires retrieval improvement

Even a perfect decision rule over the **current** cap-640 candidates can score at most **0.980951** overall. Therefore a 0.998 score is mathematically impossible without raising the blocking oracle by at least:

- All: **+0.017049**
- India, if judged at 0.998 independently: **+0.026611**
- US, if judged at 0.998 independently: **+0.010415**

For the overall slice, reaching an oracle of 0.998 would require closing **89.50%** of the current retrieval-ceiling gap to perfection. India would require closing **93.01%** of its current retrieval gap to reach 0.998 on that slice.

So the correct interpretation is dual:

- retrieval is a **hard structural requirement** for the aspirational target;
- matcher/decision quality is the **larger measured near-term error budget** at the current candidate pool.

### 3. India carries a disproportionate share of both gaps

India is **40.96%** of confirmation anchors but contributes:

- **57.14%** of the total macro-F0.5 gap to perfection;
- **61.52%** of the retrieval-ceiling gap;
- **55.54%** of the within-candidate model/decision gap.

Weighted absolute macro contributions:

| Gap component | India contribution | US contribution |
|---|---:|---:|
| Total gap to 1.0 | 0.040664 | 0.030501 |
| Retrieval ceiling | 0.011719 | 0.007330 |
| Model/decision within candidates | 0.028945 | 0.023171 |

This validates India as a high-leverage slice for **both** retrieval and matcher/decision research, rather than treating the India deficit as belonging to one subsystem.

### 4. Exact current singleton-FP score budget

The selected confirmation report contains:

- all: 291 true singletons, singleton FPR 10.6529% → **31** false-positive singleton anchors;
- India: 111 singletons, 13.5135% → **15** false-positive singleton anchors;
- US: 180 singletons, 8.8889% → **16** false-positive singleton anchors.

Because a true singleton scores exactly 1 when left empty and 0 when any candidate is predicted, an oracle that changed **only those current false-positive singleton outputs** to empty, with no other side effects, would add exactly:

- all: **31 / 5000 = +0.006200** macro F0.5;
- India: **15 / 2048 = +0.007324**;
- US: **16 / 2952 = +0.005420**.

That +0.0062 overall is:

- **8.71%** of the total current gap to perfect;
- **11.90%** of the within-candidate model/decision gap.

Singleton precision is therefore meaningful, but it is not remotely sufficient by itself. The oracle singleton-only correction would move the current 0.928835 score only to **0.935035**.

### 5. Historical cap expansion converted less than half of added oracle headroom

This is **separate calibration-only context**, not selected-confirmation performance.

On the historical wide-calibration classifier, moving raw retrieval cap 80 → 640 on the same 4,389 calibration anchors changed:

- blocking oracle: 0.968226 → 0.981178, **+0.012952**;
- model macro F0.5: 0.921486 → 0.927373, **+0.005887**;
- pair recall: 0.912150 → 0.945863, **+0.033713**;
- singleton FPR: 9.9206% → 11.1111%, **+1.1905 pp**.

The measured model gain was **45.45%** of the added oracle headroom. This is consistent with the known distribution shift from widening a candidate pool: retrieval can expose positives that the matcher then fails to exploit efficiently while also exposing many more negatives. It is not a universal conversion rate and must not be transferred to the selected depth-10 confirmation result.

## Red-team / arithmetic checks

- Overall country-weighted model score reproduces the all-row score to floating-point precision.
- Overall country-weighted blocking oracle reproduces the all-row oracle to floating-point precision.
- Retrieval gap + within-candidate gap = total gap to perfect exactly (up to floating point).
- Reported singleton FPR × singleton count resolves to integer false-positive counts: 31 / 15 / 16.
- No calibration score is substituted for a confirmation score in the primary decomposition.
- The cap-80→640 comparison is explicitly isolated as historical calibration context.
- No assumption is made that retrieval and matcher gains add linearly.
- No new holdout/confirmation window, predictions, challenge rows, or leaderboard feedback are consumed.

## Error analysis / implications

The current selected system is not in a regime where “fix retrieval and the rest is done.” The cap-640 candidate pool's oracle is high, but the model/decision layer leaves **0.0521** macro points on the table relative to that oracle. Conversely, “just improve the matcher” cannot reach the aspirational target because the current retrieval oracle hard-caps it at **0.9810**.

The strongest resource allocation interpretation is therefore parallel rather than sequential:

- continue P0 retrieval work that can raise oracle, especially India and true-link misses;
- prioritize matcher/hard-negative/calibration/set-decision work that can convert existing candidate recall into official macro F0.5;
- treat singleton precision as a bounded **~+0.0062 current-score opportunity**, valuable but not the dominant gap.

## Risks

The blocking oracle is an upper bound requiring truth knowledge. The within-candidate gap is not a promise that any particular matcher can recover all 0.0521 points. Likewise, the singleton oracle uses true singleton labels and is not an implementable gate. These numbers are **error-budget bounds**, not forecasted gains.

The 0.998 target is aspirational; requiring oracle ≥0.998 is a necessary condition for achieving it, not evidence that the target is attainable.

## Recommendation

**PROMOTE** this decomposition as a planning guardrail.

For experiment prioritization, require agents to identify which budget they are attacking:

- **retrieval ceiling**: current overall room ≈ **0.01905** to perfect, but at least **0.01705** oracle gain is necessary for any 0.998 path;
- **within-candidate matcher/decision**: current measured headroom ≈ **0.05212**;
- **current singleton false positives**: exact oracle correction budget ≈ **0.00620**.

Do not interpret those budgets as additive achievable gains. Use them to keep the swarm from declaring victory after moving one subsystem while the other remains the limiting factor.
