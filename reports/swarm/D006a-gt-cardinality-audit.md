# D006a — Ground-truth cardinality and source-multiplicity audit

## Hypothesis

True match-set cardinality and Source-2/Source-3 multiplicity may differ enough by country or source to justify country-specific cardinality priors, source-specific thresholds, or joint-source set decisions. This audit measures the label-side structure before spending a model experiment on that assumption.

## Change

Added an aggregate-only audit helper, `src/ber/truth_cardinality.py`, plus focused tests. The helper reads only supplied `train_source1.tsv` and `train_ground_truth.tsv`, reproduces the repository's deterministic 30,000-anchor development sample and 60/15/15/10 fold assignment, and emits cardinality/source-composition summaries. It does not inspect S2/S3 text and does not change retrieval, features, matching, thresholds, or submission behavior.

## Protocol

Data: complete supplied training Source 1 and complete training ground truth, not a sample for the population results.

- Source-1 bytes: 210,069,713
- Ground-truth bytes: 127,015,583
- Source-1 rows: 2,206,821
- Ground-truth rows: 2,206,821
- Positive labeled edges: 7,638,365
- Countries: 1,323,633 US anchors; 883,188 India anchors
- Deterministic development sample: 30,000 smallest `md5('sample517:' || entity_id)` values, matching the existing blocker/experiment protocol
- Fold assignment: first 8 hex digits of `sha256('fold517:' || entity_id)` modulo 100; fit <60, early <75, calibrate <90, otherwise holdout
- Official row score used for analytical cardinality sensitivity: `1.25 * TP / (1.25 * TP + FP + 0.25 * FN)` with the published singleton convention

Reproduction command:

```bash
PYTHONPATH=src python -m ber.truth_cardinality \
  --source1 /path/to/train_source1.tsv \
  --truth /path/to/train_ground_truth.tsv \
  --out /tmp/d006a-cardinality.json \
  --sample-size 30000 --quiet
```

Focused tests:

```bash
PYTHONPATH=src python -m unittest tests/test_truth_cardinality.py -v
```

The repo-ready helper completed the full 2,206,821-anchor pass in **35.98 s CPU-reported runtime / 37.68 s wall time** in this ChatGPT analysis runtime. A prior independent prototype pass produced identical integrity, cardinality, country, development-fold, and metric-sensitivity aggregates. The repo helper additionally reports exact S2/S3 count distributions and means.

## Results

### Integrity

All 2,206,821 Source-1 anchors have exactly one truth row. There are no unknown truth anchors, missing truth anchors, duplicate truth-anchor rows, duplicate target IDs within a truth row, or unexpected target-source prefixes. Thus the cardinality summaries are over the complete labeled anchor population.

### Full-population cardinality

| Statistic | Value |
|---|---:|
| Singleton (`|T|=0`) | 123,247 / 2,206,821 = **5.5848%** |
| Exactly one true match | 119,157 / 2,206,821 = **5.3995%** |
| At least two true matches | **89.0157%** |
| At least three true matches | **72.0133%** |
| At least five true matches | **26.0215%** |
| Mean true matches / anchor | **3.4613** |
| Median | **3** |
| p90 / p95 / p99 | **6 / 6 / 8** |
| Maximum | **11** |

Exact total-cardinality counts are: 0: 123,247; 1: 119,157; 2: 375,212; 3: 530,841; 4: 484,115; 5: 321,957; 6: 164,868; 7: 63,968; 8: 18,680; 9: 4,205; 10: 534; 11: 37.

This is emphatically not a mostly-one-to-one matching problem: only 5.72% of non-singletons have exactly one labeled target, while the median non-singleton has multiple targets.

### Source multiplicity

Across all anchors there are 3,693,619 S2 positive edges and 3,944,746 S3 positive edges, or 1.674 S2 and 1.788 S3 matches per anchor on average. S2 has at most 5 labeled matches per anchor; S3 has at most 6.

| Truth-source composition | Anchors | All-anchor rate | Rate among non-singletons |
|---|---:|---:|---:|
| Both S2 and S3 | 1,776,047 | **80.4799%** | **85.2404%** |
| S2 only | 143,029 | 6.4812% | 6.8646% |
| S3 only | 164,498 | 7.4541% | 7.8950% |
| Singleton | 123,247 | 5.5848% | — |

The Pearson correlation between per-anchor S2 and S3 positive counts is only **0.1199**. Joint-source presence is common, but equal or tightly coupled cardinalities are not. A decision layer may use agreement across S2/S3 as evidence, but it should not enforce matching one source merely because the other source has matches.

### US vs India

Country-level cardinality is strikingly similar:

| Statistic | India | US | India − US |
|---|---:|---:|---:|
| Anchors | 883,188 | 1,323,633 | — |
| Singleton rate | 5.5878% | 5.5828% | **+0.0050 pp** |
| Mean true matches | 3.4645 | 3.4591 | **+0.0055** |
| Both-source rate | 80.5021% | 80.4651% | +0.0370 pp |
| S2/S3 count correlation | 0.1195 | 0.1203 | -0.0008 |

For singleton prevalence, the India-US difference is 0.0050 percentage points with an approximate 95% interval of **[-0.0568, +0.0669] pp** (`z≈0.16`). The mean-cardinality difference is only 0.0055 matches; its approximate 95% interval is **[0.0009, 0.0101]**, statistically detectable solely because there are more than two million anchors and practically tiny.

**Result:** the label-side evidence does not support a useful country-specific cardinality prior for US versus India.

### Development-protocol drift

The helper exactly reproduces the existing 30,000-anchor fold sizes, including the known 4,389-anchor calibration population and its 252 singletons:

| Fold | Anchors | Singleton rate | Mean truth cardinality | Singleton-rate delta vs full |
|---|---:|---:|---:|---:|
| fit | 17,990 | 5.3030% | 3.4636 | -0.2819 pp |
| early | 4,570 | 5.5799% | 3.4803 | -0.0050 pp |
| calibrate | 4,389 | 5.7416% | 3.4805 | +0.1568 pp |
| holdout | 3,051 | 6.5225% | 3.4428 | **+0.9376 pp** |

The holdout's singleton prevalence is modestly higher than the full population (`z≈2.26` under a simple proportion comparison). That is not evidence of a bug; it is a warning that a learned or hand-set cardinality prior should be fitted out-of-fold rather than tuned to one relatively small partition.

### F0.5 consequences of wrong set size

Under the official per-anchor F0.5 metric, if every selected member up to the true set size is correct, then:

| True size | Predict one too few | Predict exact | Predict one extra FP |
|---:|---:|---:|---:|
| 1 | 0.0000 | 1.0000 | 0.5556 |
| 2 | 0.8333 | 1.0000 | 0.7143 |
| 3 | 0.9091 | 1.0000 | 0.7895 |
| 4 | 0.9375 | 1.0000 | 0.8333 |
| 5 | 0.9524 | 1.0000 | 0.8621 |

For every true cardinality >=2, one additional false positive costs more row score than omitting one otherwise-correct match. This directly supports precision-aware set decoding or expected-F0.5 selection rather than blindly filling a predicted cardinality.

## Error analysis

Three decision risks are visible from the label structure alone:

1. **Single-source entities are real.** 14.76% of non-singletons have positives in only S2 or only S3. A rule requiring support from both sources would create systematic false negatives.
2. **Joint-source presence does not imply matched counts.** The S2/S3 count correlation is only ~0.12. Hard symmetry between source cardinalities is unjustified.
3. **Fold prevalence moves enough to matter for singleton decisions.** The 3,051-anchor holdout is almost 0.94 percentage points more singleton-heavy than the full training population. A fixed prevalence assumption can look better or worse depending on which small split happens to be inspected.

## Interpretation

The country-specific version of the hypothesis is rejected: US and India have essentially the same truth-cardinality distribution. Country-aware decision improvements need evidence from candidate quality/calibration, not from a different country-level set-size prior.

The broader cardinality hypothesis remains useful. The task is overwhelmingly multi-match, both sources usually contribute positives, S3 is modestly denser than S2, and the official metric penalizes an extra false member sharply. These facts make **D006 cardinality prediction / expected set-size evidence** and **D008 joint S2/S3 evidence** reasonable follow-ups, provided they use pair scores and are evaluated end-to-end rather than converting these population priors into hard rules.

## Risks

- This is a label-structure audit, not a matcher/decision experiment. It does **not** claim an end-to-end macro F0.5 gain.
- S2/S3 raw text was not needed. Their complete files remain above this chat's Drive transfer ceiling, but target IDs in the supplied ground truth are sufficient for source multiplicity counts.
- Source prefixes are used only to aggregate label structure; record IDs are not predictive features.
- France has no labels. None of the US/India prevalence measurements should be treated as a French prior.
- Approximate confidence intervals above treat anchors as independent descriptive units; they are used only to distinguish practical from sampling-scale differences, not as a competition guarantee.

## Recommendation

**FOLLOW-UP.** Reject a country-specific cardinality prior based on US-vs-India label structure. Promote two narrower experiments: (1) source-aware / out-of-fold cardinality evidence inside D006 or expected-F0.5 set selection, and (2) D008 joint-source confidence features that treat cross-source agreement as soft evidence rather than a hard requirement.

## Follow-up tasks

- D006: estimate cardinality from inference-safe candidate-score/evidence features and compare against the same candidate set with official macro F0.5, singleton FP rate, US/India slices, and out-of-fold calibration.
- D008: test whether strong S2 and S3 evidence for the same anchor improves precision, while explicitly preserving legitimate S2-only/S3-only predictions.
- Any source-specific threshold experiment should account for the modestly higher S3 truth multiplicity rather than assuming equal source priors.
