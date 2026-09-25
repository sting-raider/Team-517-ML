# F007a — Full Source-1 token discriminativeness / IDF audit

**Issue:** #106  
**Branch:** agent/r/F007a-s1-token-idf-audit  
**Recommendation:** **FOLLOW-UP**

## Hypothesis

The current blocker keeps lexical keys only when target-side posting frequency is at most 1000 and queries only the four rarest eligible token-like keys per anchor. Source-1 document-frequency structure may reveal whether those policies cover US and India equivalently, especially given the weaker measured India end-to-end score.

This is a full-population Source-1 forensic audit. It does not claim an end-to-end retrieval or macro-F0.5 gain because complete S2/S3 target files exceed this chat runtime's 256 MiB Drive transfer ceiling.

## Change

Added src/ber/token_idf_audit.py, a dependency-free bounded-memory two-pass audit for the blocker's direct lexical channels:

- name words (w): normalized tokens of length at least 3;
- address words (u): normalized nonnumeric tokens of length at least 3 after the blocker's stoplist.

The helper computes country-local document frequencies, posting mass, rare-key coverage, four-rarest-key truncation, digit coverage, and DF quantiles. It emits aggregate JSON only.

Added tests/test_token_idf_audit.py covering country partitioning, normalization, address stopword/numeric exclusion, and probe-limit behavior. No production retrieval, matcher, threshold, or submission behavior changes.

## Protocol

Data: complete supplied train_source1.tsv, not a sample.

- bytes: **210,069,713**
- SHA-256: **591af0e1dfeb65cab71ea6ee8cb69df00f92d6ba6fa79e05746c938775d14973**
- anchors: **2,206,821**
- US: **1,323,633**
- India: **883,188**
- empty names/addresses: **0**
- non-ASCII names: **0**
- non-ASCII addresses: **554**, all in India

Normalization mirrors repository semantics with Python unicodedata: lowercasing, accent stripping, Unicode letter/digit preservation, and separator collapse. The remaining parity risk versus DuckDB strip_accents is limited to rare Unicode behavior; only 554 Source-1 addresses are non-ASCII.

The empirical census was executed as four deterministic streaming passes to fit this runtime's per-call execution window: one DF census and one coverage pass per country. Wall times were **37.51 s US census, 38.79 s India census, 39.60 s US coverage, 38.60 s India coverage**, about **154.5 s total** over four scans. Peak observed RSS was about **317 MB**.

Synthetic validation passed: 2/2 tests.

Reproduction commands:

    PYTHONPATH=src python -m unittest tests/test_token_idf_audit.py -v

    PYTHONPATH=src python -m ber.token_idf_audit \
      --source1 /path/to/train_source1.tsv \
      --out /tmp/f007a-token-idf.json \
      --max-probes 4

No confirmation/frozen holdout or leaderboard feedback was consumed.

## Baseline

F007a changes no model, so no official metric delta is claimed. Current reference remains depth-10 CatBoost at cap 640:

- confirmation macro F0.5: **0.928835**
- candidate pair recall: **0.947246**
- blocking-oracle macro F0.5: **0.980951**
- India confirmation macro F0.5: **0.900722**

These are context only; F007a did not re-evaluate confirmation.

The relevant current blocker behavior is country-local hashing, target frequency cutoff <=1000, and at most four rarest eligible keys per lexical kind, alongside separate full-name/full-address/numeric/composite channels.

## Results

### Name words

| Metric | US | India |
|---|---:|---:|
| Vocabulary | 69,881 | 49,836 |
| Posting mass | 4,162,929 | 3,166,185 |
| Vocabulary with DF <=1000 | 99.2702% | 99.5505% |
| Posting mass with DF <=1000 | **35.0848%** | **21.3262%** |
| Anchors with any token DF <=10 | 11.0473% | 14.7399% |
| Anchors with any token DF <=100 | 38.9191% | 44.0400% |
| Anchors with any token DF <=1000 | **67.8789%** | **56.5800%** |
| Anchors with all name words DF >1000 | **32.1211%** | **43.3583%** |
| Anchors with >4 eligible-length name words | 7.8884% | 10.4971% |
| DF<=1000 keys dropped by four-probe limit | **0.0123%** | **0.1118%** |

Name DF quantiles:

- US: min 1, p25 1, p50 3, p75 11, p90 36, p95 66, p99 628, max 355,725.
- India: min 1, p25 2, p50 4, p75 10, p90 28, p95 55, p99 244, max 521,781.

The vocabulary is overwhelmingly rare, but posting mass is not. The DF<=1000 filter removes a large amount of common-token mass while retaining more than 99% of vocabulary.

India has the sharper name saturation problem: **43.36%** of anchors have no name word at or below DF 1000 versus **32.12%** in the US. This agrees directionally with F005's independent common-name collision audit and means name-only lexical retrieval has less rare-token opportunity in India.

### Address words

| Metric | US | India |
|---|---:|---:|
| Vocabulary | 104,930 | **309,602** |
| Posting mass | 3,522,071 | **6,811,230** |
| Vocabulary with DF <=1000 | 99.4930% | 99.7917% |
| Posting mass with DF <=1000 | 47.4730% | 33.3910% |
| Anchors with any word DF <=10 | 14.6799% | **41.4427%** |
| Anchors with any word DF <=100 | 40.4922% | **70.1845%** |
| Anchors with any word DF <=1000 | 86.5466% | **92.7208%** |
| Anchors with all address words DF >1000 | 13.4527% | **7.2792%** |
| Anchors with >4 eligible address words | 3.1679% | **94.3052%** |
| DF<=1000 address query keys | 1,672,031 | 2,274,335 |
| Keys dropped by four-probe limit | **205 (0.0123%)** | **170,917 (7.5150%)** |

Address-word DF quantiles:

- US: min 1, p25 1, p50 2, p75 5, p90 22, p95 71, p99 525, max 75,714.
- India: min 1, p25 1, p50 1, p75 2, p90 8, p95 21, p99 172, max 191,715.

This is the decisive result. India has fewer Source-1 anchors than the US but nearly **3x the address-word vocabulary** and almost **2x the posting mass**. Rare address evidence is also substantially more available: 41.44% of Indian anchors have an address word with DF<=10 and 70.18% have one with DF<=100.

At the same time, **94.31%** of Indian anchors have more than four eligible address words versus only 3.17% in the US. After the DF<=1000 filter, the current four-rarest address-word probe limit is almost lossless in the US but discards **170,917 / 2,274,335 = 7.52%** of eligible low-DF Indian address keys.

### Numeric-address opportunity

| Metric | US | India |
|---|---:|---:|
| Anchors with any address digit | **99.5830%** | **86.4813%** |
| Distinct digit tokens | 42,211 | 10,314 |
| Digit DF p50 / p90 / p99 | 3 / 61 / 577 | 2 / 72 / 2,276 |
| Maximum digit DF | 26,662 | 103,757 |

The blocker's h/z/d channels depend on address numbers. Their anchor-side opportunity is lower in India: about **13.5%** of Indian addresses expose no digit token, versus 0.42% in the US. That raises the relative importance of nonnumeric address lexical evidence in India.

## Error analysis

1. **Common-name saturation is worse in India.** A large India slice lacks any rare-enough name word under the current proxy threshold.
2. **Indian addresses contain abundant rare lexical evidence.** The country has much larger address vocabulary and higher per-anchor rare-word coverage.
3. **The fixed four-address-word probe budget is asymmetric.** It trims 0.012% of eligible US keys but 7.515% of eligible India keys.
4. **Number-based rescue is less universal in India.** Lower digit coverage means numeric/composite channels cannot compensate for lexical truncation on every anchor.

## Interpretation

The audit supports IDF/BM25-style weighting, but the more actionable result is the probe-budget asymmetry.

For name words, raising the four-probe limit is unlikely to matter much because it already retains more than 99.88% of DF<=1000 keys in both countries. For address words, the same statement is true in the US but false in India.

This motivates one focused target-side experiment: selectively increase or adapt the India address-word probe budget while keeping the final candidate cap fixed and measuring marginal recovered positives per added candidate.

## Risks / red-team checks

- No labels were used as predictive evidence; ground truth was not needed.
- entity_id was not used as a feature.
- No confirmation/frozen holdout was read.
- No external entity data was used.
- **S1-to-target transfer:** production blocker eligibility uses S2/S3 frequencies. Source-1 DF motivates hypotheses but cannot prove target-side recall.
- **Composite redundancy:** v adjacent-word-pair and d number+word keys may already recover candidates an extra u probe would find.
- **Candidate-size constraint:** organizer guidance favors smaller candidate pools. Any widened probe experiment must hold final cap constant or explicitly report size tradeoffs.
- Python accent stripping is not bit-identical to DuckDB for every rare Unicode case; the affected Source-1 population is tiny.

## Recommendation

**FOLLOW-UP.** Do not change production blocking from this audit alone.

The highest-value next empirical test is a same-slice target-side ablation at fixed final cap comparing address-word probe budgets 4 vs 6/8 or an adaptive lexical-richness budget, with US/India slices. Required metrics: pair recall, entity recall, all-matches-retrieved rate, blocking-oracle macro F0.5, candidate-count quantiles, marginal recovered/lost positives, and runtime/memory.

Interactions with active work:

- **R005 BM25 name:** use country/source-local DF and explicit commonness; name BM25 alone should not be assumed to close India because 43.4% of Indian anchors lack a DF<=1000 name word under this S1 proxy.
- **R006 BM25 address:** prioritize India slices; the census shows richer rare address evidence there.
- **future blocker variant:** test larger/adaptive India address-word probe budgets rather than globally widening every lexical kind.

No official macro-F0.5 gain is claimed until complete target-side evaluation is performed on the exact current development/calibration anchors.
