# X011 — INT003 test cardinality drift vs labeled train priors

## Hypothesis

INT003's unlabeled test output set sizes may drift away from supplied labeled training truth structure. Same-country US/India drift can identify a decision/calibration warning without using test labels, while France can only be compared to the labeled operating envelope as a robustness diagnostic.

This experiment **does not infer France labels** and does not treat train cardinality as test truth.

## Exact change

Added `src/ber/v3_cardinality_drift.py`, an aggregate-only helper that:

1. streams complete supplied `train_source1.tsv`;
2. streams complete supplied `train_ground_truth.tsv`;
3. computes exact truth-cardinality priors overall and by country;
4. reads committed `reports/int003_test_country_drift.json`;
5. compares v2/v3 predicted mean set size and empty-prediction rate to labeled train priors.

No retrieval, matcher, threshold, or submission behavior changes.

## Protocol

Data/evidence:

- complete `train_source1.tsv`: **2,206,821** Source-1 anchors;
- complete `train_ground_truth.tsv`: **2,206,821** truth rows;
- committed full-test aggregate output: `reports/int003_test_country_drift.json`;
- D006a's completed full-population country cardinality audit for exact study provenance and rounded country-level prior values.

No sampling was used for the population aggregates. No S2/S3 raw text, confirmation/frozen holdout, leaderboard feedback, external entity data, or France labels were used.

### Execution note

The private Python/container runtime in this chat returned a session-level `ClientError` before user code executed. I did **not** substitute a sample.

The mounted raw files remained accessible through the Files backing-file parser, so I independently scanned the complete truth file with anchored cardinality regexes. The exact counts reproduced D006a for every cardinality 0–11:

`0:123247, 1:119157, 2:375212, 3:530841, 4:484115, 5:321957, 6:164868, 7:63968, 8:18680, 9:4205, 10:534, 11:37`.

I also independently reproduced Source-1 country row counts: **1,323,633 US** and **883,188 India**. Country-specific truth means/singleton rates below reuse the completed full-data D006a audit rather than pretending an unavailable local join reran.

The new helper is therefore a reproduction/handoff artifact; it was **not executed in this chat**.

Normal reproduction command:

```bash
PYTHONPATH=src python -m ber.v3_cardinality_drift \
  --source1 /path/to/train_source1.tsv \
  --truth /path/to/train_ground_truth.tsv \
  --test-drift reports/int003_test_country_drift.json \
  --out /tmp/x011.json
```

## Baseline labeled cardinality structure

The complete train truth has **7,638,365** positive edges, mean cardinality **3.461253**, and singleton rate **5.584821%**.

| Labeled train population | Anchors | Mean true matches | Singleton rate |
|---|---:|---:|---:|
| India | 883,188 | 3.4645 | 5.5878% |
| US | 1,323,633 | 3.4591 | 5.5828% |
| Overall | 2,206,821 | 3.461253 | 5.584821% |

The India-US truth-prior difference is practically negligible, consistent with D006a. This is important: there is no label-side basis for a hard India-vs-US cardinality prior.

## Results

### Same-country US/India transport diagnostic

| Country | Train truth mean | v2 test predicted mean | v3 test predicted mean | v3 gap | Absolute mean-gap reduction vs v2 |
|---|---:|---:|---:|---:|---:|
| India | 3.4645 | 2.982622 | 3.080473 | -0.384027 | **20.31%** |
| US | 3.4591 | 3.252112 | 3.307800 | -0.151300 | **26.90%** |

INT003 therefore moves predicted cardinality **toward**, not away from, the labeled same-country train prior in both labeled countries.

The same is true for the zero-output mass:

| Country | Train singleton rate | v2 test empty rate | v3 test empty rate | v3 gap vs train | Absolute gap reduction vs v2 |
|---|---:|---:|---:|---:|---:|
| India | 5.5878% | 7.163951% | 6.851723% | +1.263923 pp | **19.81%** |
| US | 5.5828% | 5.969634% | 5.758506% | +0.175706 pp | **54.58%** |

These are output-distribution diagnostics only. A predicted-empty anchor is not necessarily a true singleton, and a nonempty prediction says nothing by itself about correctness.

If the same-country train mean were transported to test as a purely counterfactual reference, INT003 emits about **311,056 fewer India matches** and **100,328 fewer US matches** than that reference. Those numbers are not estimated false negatives; they only express the scale of aggregate output drift.

### France unlabeled robustness diagnostic

France has no supplied labels. Its INT003 output remains outside the labeled US/India cardinality envelope:

- v3 France mean predictions/entity: **4.358710**;
- labeled US/India train mean envelope: **3.4591–3.4645**;
- France is **+0.894210** predictions/entity above the higher labeled mean;
- transported literally, that difference corresponds to about **232,005–233,406** extra predicted links over the labeled-mean envelope across 259,452 French anchors;
- v3 France empty-prediction rate: **3.436088%**;
- labeled US/India singleton envelope: **5.5828–5.5878%**;
- France empty output is about **2.147 pp below** the lower labeled singleton rate.

V3 did move France toward the labeled cardinality range relative to v2: its distance from the labeled mean midpoint fell by **19.37%** (v2 mean 4.574129 → v3 4.358710). That is mildly reassuring, but the remaining gap is still large enough to deserve robustness attention.

### Overall aggregation hides the country pattern

Across all test countries, INT003 predicts **5,819,438** links for 1,732,544 anchors, mean **3.358898**, only -0.102355 below the all-train truth mean.

That apparently modest overall gap is misleading because opposite country effects partly cancel: US/India outputs are below their labeled train means while France is substantially above the labeled range. Country-conditioned diagnostics are therefore more informative than one global set-size mean.

## Relationship to official score

This experiment does **not** claim a macro F0.5 delta. The current confirmed INT003 score remains **0.950198** on the already-consumed 45,001–50,000 confirmation window.

The findings only constrain follow-up design:

- they do **not** support hard country cardinality priors for US versus India;
- they do support evaluating candidate-score/cardinality-aware set decoding out of fold;
- France output density should be treated as a transfer-risk signal, not "corrected" to US/India counts without labels.

## Error analysis / red-team checks

1. **Truth/prediction semantics differ.** Train singleton rate is a label property; test empty rate is a model-output property. Their difference is not an error rate.
2. **Train→test cardinality transport is an assumption.** Same-country test truth can legitimately differ from train truth. Counterfactual edge gaps are descriptive only.
3. **France is unlabeled.** The France envelope comparison cannot say whether 4.36 matches/entity is too many or too few.
4. **Only two test moments are committed.** `int003_test_country_drift.json` exposes mean predicted cardinality and zero-output mass, not the full predicted-cardinality histogram. No uncommitted prediction file was fabricated or approximated.
5. **Country priors were cross-checked, not silently re-estimated.** The raw full-file scan independently reproduced all overall cardinality counts and Source-1 country counts; country-level mean/singleton priors reuse D006a's completed full-population audit because the local join runtime was unavailable.
6. **No ID-as-feature leakage.** Entity IDs are used only to join supplied train Source-1 to supplied truth in the reproduction helper.

## Recommendation

**FOLLOW-UP.**

Do **not** introduce a hard country-specific set-size prior. US and India truth cardinality is essentially identical, and INT003 already moved both countries' test output aggregates closer to that labeled structure than v2.

The useful next decision experiment is an out-of-fold cardinality/expected-F0.5 decoder driven by candidate probabilities, score gaps, provenance, and source evidence. For France, preserve language-agnostic evidence and audit score/cardinality distributions; do not force the output to match US/India priors.

## Artifacts

- helper: `src/ber/v3_cardinality_drift.py`
- aggregate JSON: `reports/swarm/X011-v3-cardinality-drift.json`
- report: `reports/swarm/X011-v3-cardinality-drift.md`
- Issue: #202
