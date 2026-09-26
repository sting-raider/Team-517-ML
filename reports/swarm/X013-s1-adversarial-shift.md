# X013 — Same-country Source-1 adversarial train-vs-test shift audit

**Issue:** #234  
**Branch:** `agent/x/X013-s1-adversarial-shift`  
**Recommendation:** **REJECT** the same-country Source-1 format-shift hypothesis at this sensitivity; **FOLLOW-UP** target-side / candidate-distribution shift instead.

## Hypothesis

A language-agnostic Source-1 character n-gram domain classifier may detect same-country train-vs-test text-format shift that coarse aggregate audits miss. If US or India train-vs-test rows are distinguishable above chance from permitted Source-1 text alone, the strongest non-ID cues could motivate normalization or robustness work before another submission.

## Change

No production retrieval, matcher, feature, threshold, or submission behavior changed.

This recovery completed the previously blocked X013 forensic with:

- a complete raw Source-1 population census for train and test;
- deterministic same-country adversarial validation using business name/address text only;
- structural, name-char, address-char, and joint-char views;
- grouped train/eval splitting so identical normalized country+joint text cannot appear on both sides of the classifier split;
- a shuffled-label null control;
- an independent deterministic replication sample;
- a small regularization sweep and bootstrap interval for the primary joint result.

The helper is `tools/experiments/x013_s1_adversarial_shift.py`; focused tests are in `tests/test_x013_s1_adversarial_shift.py`.

## Protocol

### Data and compliance

Complete supplied files were transferred from the shared Drive and read directly:

- `train_source1.tsv`: **210,069,713 bytes**, 2,206,821 anchors
- `test_source1.tsv`: **175,022,086 bytes**, 1,732,544 anchors

Population counts:

| Split | US | India | France |
|---|---:|---:|---:|
| Train S1 | 1,323,633 | 883,188 | 0 |
| Test S1 | 663,106 | 809,986 | 259,452 |

Only `business_name`, `business_address`, `country`, and split membership were read for the adversarial task. Record IDs were excluded from the dataframe entirely. No S2/S3 records, match labels, confirmation/frozen holdouts, external business data, France pseudo-labels, or leaderboard feedback were used.

Production normalization was grounded from `src/ber/data.py`: lowercase + accent stripping + collapse non-letter/non-number runs + trim. The Python runner uses NFKD mark removal as the local semantic mirror because DuckDB is unavailable in this runtime.

### Full-population census

The raw Source-1 files were scanned in full, not sampled, to measure row counts and simple structural summaries before fitting any domain classifier.

Same-country train/test means are nearly identical:

| Country | Metric | Train | Test | Test - train |
|---|---|---:|---:|---:|
| US | mean name length | 22.465108 | 22.463308 | -0.001800 |
| US | mean address length | 34.962432 | 34.966117 | +0.003685 |
| India | mean name length | 26.386305 | 26.374771 | -0.011534 |
| India | mean address length | 77.699632 | 77.713843 | +0.014211 |
| US | address digits / row | 4.166718 | 4.167421 | +0.000703 |
| India | address digits / row | 3.857121 | 3.857399 | +0.000278 |

This independently reproduces the earlier F011 conclusion that the obvious Source-1 format dimensions are stable within country.

### Classifier sample

A full-population 3–5 gram stream was attempted, but the private Python execution surface enforces an approximately **60 second** call cap. The full stream was interrupted before a valid full-population classifier metric existed. Per the preregistered X013 fallback, the classifier portion is therefore explicitly a **Tier-1 deterministic sample**, not a silent full-data claim.

Primary sample:
- 60,000 train + 60,000 test rows per country;
- 240,000 rows total;
- sample chosen by smallest deterministic text hashes, not IDs;
- fold 0 of 5 held out by hash of `country + normalized(name+address)`;
- identical normalized text is grouped into the same fold.

Primary models:
- structural baseline: 22 text-structure features + standardized logistic regression;
- char views: `HashingVectorizer`, character 3–5 grams, (2^{18}) bins;
- averaged SGD log-loss classifier, balanced class weights;
- primary seed 517.

Replication:
- separate salt;
- 30,000 train + 30,000 test rows per country;
- 120,000 rows total;
- joint char view only.

## Results

Chance AUROC is 0.5. Every measured same-country view is effectively at chance.

### Primary sample

| Country | View | AUROC | AUPRC | Balanced accuracy |
|---|---|---:|---:|---:|
| US | structural | 0.499859 | 0.499428 | 0.499710 |
| US | name char | 0.499097 | 0.498209 | 0.500005 |
| US | address char | 0.502432 | 0.499365 | 0.503422 |
| US | joint char | **0.504140** | 0.499425 | 0.502927 |
| US | shuffled-label joint null | 0.499179 | 0.496925 | 0.502645 |
| India | structural | 0.493144 | 0.495143 | 0.494103 |
| India | name char | 0.497442 | 0.495672 | 0.500375 |
| India | address char | 0.505000 | 0.503199 | 0.502910 |
| India | joint char | **0.504927** | 0.502265 | 0.502618 |
| India | shuffled-label joint null | 0.495825 | 0.496836 | 0.495102 |

Primary joint eval sizes:
- US: 23,831
- India: 24,088

Entity-row bootstrap on the held-out joint predictions, 200 replicates:
- US AUROC 95% interval: **[0.495746, 0.510124]**
- India AUROC 95% interval: **[0.498206, 0.511701]**

Both include 0.5.

### Independent replication

| Country | Joint AUROC | AUPRC | Balanced accuracy |
|---|---:|---:|---:|
| US | **0.502083** | 0.507163 | 0.497752 |
| India | **0.496464** | 0.501551 | 0.498967 |

The replication does not reproduce even the tiny +0.004 to +0.005 primary AUROC deviations.

### Regularization sanity sweep

Primary-sample joint AUROC across `alpha ∈ {1e-5, 1e-6, 1e-7}`:

- US: **0.501735–0.503883**
- India: **0.503450–0.505456**

No setting reveals a material domain signal. Some SGD runs hit the configured iteration ceiling, but changing regularization and extending to 40 iterations did not move AUROC out of the chance neighborhood.

## Error analysis

The intended X013 failure mode was hidden within-country Source-1 drift that simple means/rates miss. The experiment finds no useful evidence for it.

Three observations matter:

1. **Coarse full-population structure is stationary.** Mean lengths and digit burden move by tiny amounts within US and India.
2. **Higher-order character structure is also not detectably separable on two independent samples.** Name, address, and joint 3–5 gram classifiers remain at chance.
3. **The null behaves like the real classifier.** Shuffled-label AUROC is near 0.5, and the real-model bootstrap intervals overlap chance.

Because the classifier result is sampled rather than full-population, this is not proof that every rare formatting pocket is identical. It is evidence that any broad same-country Source-1 domain signal is too weak to justify a P0 adaptation cycle.

No “top diagnostic n-grams” are reported: with AUROC at chance, ranking noisy coefficients would manufacture a story from sampling noise.

## Red-team checks

- **ID leakage:** record IDs are never loaded by the helper.
- **Label leakage:** match truth is never read.
- **Country confounding:** classifiers are trained/evaluated separately within US and India.
- **Exact-text leakage:** split assignment hashes normalized country+joint text, keeping identical normalized text on one side of the classifier split.
- **Sampling artifact:** a separate deterministic sample/salt was run; the tiny primary deviations did not replicate.
- **Hyperparameter artifact:** a three-point alpha sweep remained near chance.
- **Null control:** shuffled training labels give chance performance.
- **Confirmation/leaderboard contamination:** neither is read or used.
- **France labels:** none are invented.

## Runtime

Measured successful phases in this recovery runtime:

- full-population census: 17.6 s
- primary deterministic sample construction: 13.6 s
- primary multi-view modeling: 55.5 s
- independent replication: 25.8 s
- alpha sweep: 50.1 s
- bootstrap interval: 26.1 s
- focused tests: 3/3 passed

A full-population joint char-stream attempt was interrupted by the execution surface's ~60 s call limit before yielding a valid metric.

## Risks

- The adversarial classifier metrics are Tier-1 deterministic samples, not full-population sparse fits.
- The Python accent normalization is a semantic mirror rather than byte-for-byte DuckDB `strip_accents()` parity.
- Hashing-vectorizer collisions can reduce classifier power, although (2^{18}) bins, independent replication, and the regularization sweep make a large hidden signal unlikely.
- X013 covers Source-1 only. S2/S3 formatting, candidate density, retrieval-score distributions, and target-side commonness can still shift materially.
- A null Source-1 drift finding says nothing about France matching accuracy.

## Recommendation

**REJECT** the hypothesis that a material, broad same-country Source-1 train→test format shift is currently a useful optimization target.

Do not spend a competition-critical cycle on US/India Source-1 punctuation or character-format adaptation based on this evidence. The stronger known risks are:

1. India remains the weaker labeled slice and is more prevalent in test than in train.
2. France is unseen in labels and structurally distinct.
3. Target-side / candidate-density distributions were not tested here.
4. Retrieval and decision errors remain much larger than any detectable Source-1 domain signal.

A higher-value follow-up is a target-side shift audit on S2/S3 or cached INT003 candidate outputs: candidate counts, retrieval score/rank distributions, key-hit provenance, and matcher-score calibration by source/country, without using test labels.

## Artifacts

- `tools/experiments/x013_s1_adversarial_shift.py`
- `tests/test_x013_s1_adversarial_shift.py`
- `reports/swarm/X013-s1-adversarial-shift.json`
- `reports/swarm/X013-s1-adversarial-shift.md`
- `experiments/REGISTRY.tsv`
