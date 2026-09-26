# M001b — Train/test transfer audit for token-IDF profiles

**Issue:** #265  
**Branch:** `agent/x/M001b-idf-transfer-audit`  
**Stacked on:** M001a #262 / PR #264  
**Recommendation:** **PROMOTE-EMPIRICAL-GATE**

## Scientific question

M001a showed that country/field-local IDF weighting can distinguish loss of rare business evidence from loss of common evidence that the current unweighted token overlap treats identically. Before paying the engineering cost of a full INT003 ablation, M001b asks whether split-local IDF itself introduces a train→test transfer problem.

If token commonness moves materially between train and test, a model trained on train-local IDF features could see a shifted feature distribution at inference even when the underlying pair evidence is comparable.

## Change

No production retrieval, matcher, feature schema, threshold, or submission behavior changed.

Added a transfer-audit helper and focused tests on top of M001a:

- `tools/experiments/m001b_idf_transfer_audit.py`
- `tests/test_m001b_idf_transfer_audit.py`
- aggregate JSON and this report

The helper uses the exact M001a normalization, token sets, and smoothed IDF:

[
w(t)=\log\left(\frac{N_{country}+1}{df_{country,field}(t)+1}\right)+1.
]

## Protocol

### Data

Complete supplied Source-1 files:

- train: **2,206,821** rows
- test: **1,732,544** rows
  - US: 663,106
  - India: 809,986
  - France: 259,452

No sampling was used.

The exact full train profiles generated in the immediately preceding M001a run were reused. Test US, India, and France profiles were independently scanned over the complete 175,022,086-byte test Source-1 file.

No S2/S3 records, match labels, confirmation/frozen holdout, leaderboard feedback, external entity data, or France pseudo-labels were used. Record IDs are not predictive evidence.

### Transfer metrics

For US and India, name/address profiles are compared on:

- fraction of test vocabulary unseen in same-country train;
- fraction of **test posting mass** contributed by unseen tokens;
- Spearman correlation of shared-token normalized document frequencies;
- test-posting-weighted absolute train/test IDF drift;
- posting-weighted IDF quantiles in each split.

The distinction between vocabulary novelty and posting-mass novelty is important. A corpus can contain many one-off new tokens while nearly all token occurrences still live on a stable shared vocabulary.

France has no labeled/train country counterpart. It is therefore reported only as a test-local, unlabeled reference. No France accuracy or transfer score is invented.

## Results

### US/India posting-weighted IDF is highly stable

| Country | Field | Shared-DF Spearman | Test vocab unseen | Test posting mass unseen | Median |IDF drift| | Mean weighted |IDF drift| |
|---|---|---:|---:|---:|---:|---:|
| US | name | 0.8674 | 14.2365% | **0.4387%** | **0.0171** | 0.0643 |
| US | address | 0.8660 | 25.0540% | **0.8135%** | **0.0148** | 0.0642 |
| India | name | 0.8398 | 13.1368% | **0.3332%** | **0.0064** | 0.0490 |
| India | address | 0.8010 | **52.5007%** | **1.9529%** | **0.0077** | 0.0435 |

The apparent India-address vocabulary shift is mostly a rare-token tail. More than half of distinct test address tokens do not occur in train India, but those tokens account for only **1.95% of address-token postings**.

That distinction matters for model exposure: a large vocabulary novelty number looks alarming until it is weighted by how often those tokens actually occur.

### IDF feature support barely moves at the center

Posting-weighted IDF median:

| Country | Field | Train | Test | Test - train |
|---|---|---:|---:|---:|
| US | name | 6.6601 | 6.6671 | +0.0070 |
| US | address | 6.8847 | 6.8785 | -0.0062 |
| India | name | 5.4173 | 5.4178 | +0.0005 |
| India | address | 5.2106 | 5.2081 | -0.0025 |

The full posting-weighted quantile curves are similarly close in the aggregate JSON.

Only a small fraction of shared-token test posting mass experiences large IDF movement:

| Country | Field | Posting mass with |IDF drift| > 0.5 |
|---|---|---:|
| US | name | 2.5758% |
| US | address | 2.3174% |
| India | name | 1.8443% |
| India | address | **1.3855%** |

Thus the proposed normalized split-local commonness measure is not showing the kind of same-country shift that would invalidate an empirical matcher gate.

## France reference

France is structurally different, particularly in addresses.

Test-local posting-weighted IDF median:

- France name: **4.8871**
- France address: **3.0148**

For comparison, labeled-train address medians are 6.8847 US and 5.2106 India. French address token occurrences are therefore much more concentrated on common tokens under this representation.

However, the feature does not collapse to a constant in France. Repeating the controlled M001a rare-vs-common deletion probe with **France test-local** profiles gives:

| Field | Mean weighted gap | Median gap | Share gap ≥ 0.10 |
|---|---:|---:|---:|
| name | **0.3265** | 0.3320 | 96.6259% |
| address | **0.2493** | 0.2463 | 99.9248% |

Median selected rare/common token DF:

- France name: 61 vs 22,672
- France address: 61 vs 201,962

So France's absolute commonness distribution is shifted, but relative token distinctiveness remains strong. This supports using **normalized split-local IDF similarities**, not raw document-frequency counts, if M001 advances.

## Validation / red team

The authored dependency-light checks cover weighted quantiles, average ranks with ties, Spearman direction, and synthetic profile comparison.

During execution, the initial synthetic expectation incorrectly required <0.02 IDF drift for exactly proportional tiny DFs. The `+1` smoothing term makes that false at small counts; measured drift is ~0.0502. The test was corrected to the mathematically appropriate <0.06 bound rather than changing the implementation to satisfy a bad assertion.

After correction:

- authored semantic checks: **4/4 PASS**
- 1,000 randomized tied-rank arrays compared against `scipy.stats.spearmanr`: **1,000/1,000 PASS**
- maximum observed Spearman implementation error: approximately (5.6\times10^{-17})

This correction is preserved because a passing wrong test is not evidence, merely optimism wearing a lanyard.

## Runtime

Incremental M001b work in this chat:

- complete test US profile scan: 17.90 s
- complete test India profile scan: 29.51 s
- complete test France profile scan: 9.71 s
- complete France controlled probe: 12.69 s
- total incremental measured Python time: **69.82 s**

The complete train profiles were reused from M001a's immediately preceding full-population census, not sampled or reconstructed from aggregates.

## Interpretation

M001b does **not** find a same-country Source-1 transfer reason to reject M001.

The central result is stronger than raw vocabulary overlap suggests:

- US/India split-local posting-weighted IDF support is almost unchanged at the median;
- novel test-token posting mass is below 2% in all four country/field slices;
- large shared-token IDF drift affects only a small fraction of posting mass;
- the India-address long tail is enormous in vocabulary count but low in occurrence mass.

France remains an out-of-domain concern because its address commonness distribution is shifted. Still, the controlled relative-distinctiveness signal is at least as strong as the labeled-country probes, and weighted-overlap features are normalized rather than raw-frequency features.

## Risks

1. This is **Source-1 transfer evidence only**. Production M001 needs complete target-side S2/S3 token profiles for both training materialization and test inference.
2. Shared-token Spearman is vocabulary-weighted; the more decision-relevant posting-weighted drift metrics are reported separately.
3. France remains unlabeled. Strong feature dynamic range does not imply France accuracy.
4. The `+1` IDF smoothing is intentionally retained; rare tiny-count tokens can show larger split drift even under proportional rates.
5. Numeric tokens are included and can overlap M003 commonness signals.

## Recommendation

**PROMOTE-EMPIRICAL-GATE.**

For the full M001 gate:

- use country/field-local **normalized IDF**, not raw counts;
- construct profiles independently but identically on the permitted train and test inventories;
- keep M001 opt-in and evaluate it alone before combinations with M003/M009;
- use the exact INT003 fused cap-160 candidate sets and unchanged retrieval;
- preserve fit/early/calibration splits and tune only on calibration;
- report official macro F0.5, US/India, singleton FPR, threshold, paired anchor deltas, candidate recall/oracle parity, runtime, and memory;
- add France feature-distribution diagnostics, but do not use France pseudo-labels.

M001a established representational value; M001b removes the most obvious Source-1 transfer objection. The remaining gate is target-side implementation plus actual labeled same-candidate matcher evaluation.
