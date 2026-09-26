# F006a — Legal-form suffix stripping collision-risk audit

## Hypothesis

Conservative legal-form suffix stripping might improve lexical retrieval robustness across US, India, and unseen-France, but unconditional stripping can also collapse distinct Source-1 businesses onto the same name key and increase candidate pressure. The useful question is therefore not “are legal suffixes common?” but whether the stripped key is selective enough to deserve production retrieval weight.

## Change

No production blocker or matcher code was changed. This is a full-population Source-1 forensic audit comparing the current production-style normalized business-name key against suffix-stripped variants on the exact same rows.

The suffix families were selected from high-frequency final tokens observed in the supplied Source-1 data only. Core candidates include US forms such as LLC/Inc/Corp, India forms such as Private Limited/Pvt Ltd/Limited, and France forms such as SARL/SAS/EURL/SA/SASU/SCI/EI. Generic semantic endings such as “group”, “trust”, “society”, “school”, and “foundation” were intentionally not stripped.

## Protocol

- Complete train_source1.tsv: 2,206,821 rows.
- Complete test_source1.tsv: 1,732,544 rows.
- Total audited Source-1 rows: 3,939,365.
- Countries: train US/India; test US/India/France.
- No sampling.
- No target Source-2/Source-3 rows were used because those files exceed this chat runtime's 256 MiB Drive-transfer limit.
- No France labels were invented or used.
- No external entity/business data were used.
- Record IDs were not used as features or evidence.
- Baseline key: repository-style normalization only (accent stripping, lowercase, non-letter/number runs to spaces).
- Treatment key: the same normalization followed by a conservative legal-form suffix removal.
- A “collision-exposed affected row” is a suffix-bearing row whose stripped key is shared by at least two distinct original normalized Source-1 names. Since Source-1 rows are reference anchors, this is a direct proxy for added hard-negative/candidate pressure, not evidence that the businesses are identical.
- Runtime observed in the working Python kernel: 33.6 s for full-file streaming/normalization/counter construction; the later fanout pass was about 10 s.

Current competition context is INT003 at 0.950198 macro F0.5 on its frozen 5k confirmation window. This audit does not consume a new confirmation window and does not claim an end-to-end score change.

## Results

### Full conservative core stripping

| Slice | Rows | Suffix-bearing | Unique-key retention | Collision-exposed affected rows | Duplicate-row rate baseline → stripped | Max stripped fanout | p99 added fanout |
|---|---:|---:|---:|---:|---:|---:|---:|
| train US | 1,323,633 | 56.81% | 86.84% | 38.92% | 35.81% → 47.09% | 561 | 222 |
| train India | 883,188 | 84.22% | 85.77% | 50.39% | 44.40% → 53.60% | 192 | 61 |
| test US | 663,106 | 56.75% | 89.48% | 31.11% | 29.13% → 39.36% | 269 | 116 |
| test India | 809,986 | 84.19% | 85.91% | 49.83% | 43.76% → 52.87% | 182 | 56 |
| test France | 259,452 | 68.91% | 83.55% | 45.14% | 34.41% → 48.19% | 530 | 246 |

No Source-1 stripped key exceeded fanout 1,000 in these slices. That does not prove target-source posting lists would also stay below the blocker cutoff; this is only a Source-1 proxy.

### Major-two suffix bundles

Even limiting stripping to the two dominant forms per country remains collision-heavy:

| Slice | Variant | Coverage | Collision-exposed affected rows | Unique-key retention | Max fanout |
|---|---|---:|---:|---:|---:|
| train US | LLC + Inc | 44.88% | 29.50% | 93.58% | 501 |
| test US | LLC + Inc | 44.87% | 23.71% | 94.83% | 239 |
| train India | Private Limited + Pvt Ltd | 62.65% | 43.63% | 95.59% | 144 |
| test India | Private Limited + Pvt Ltd | 62.60% | 43.29% | 95.63% | 137 |
| test France | SARL + SAS | 48.47% | 39.34% | 92.39% | 396 |

### Single dominant suffixes

The problem is not only cross-suffix collapsing:

- US train: LLC alone exposes 20.98% of affected rows to new collisions; Inc alone 22.43%.
- US test: LLC 17.97%; Inc 19.07%.
- India train: Private Limited 41.54%; Pvt Ltd 34.12%.
- India test: Private Limited 41.39%; Pvt Ltd 33.81%.
- France test: SARL 29.00%; SAS 29.24%.

### Candidate-pressure proxy

For the full core treatment, mean added same-key Source-1 fanout among suffix-bearing rows is 14.95 (train US), 11.05 (train India), 7.68 (test US), 10.13 (test India), and 13.80 (test France). The p99 added fanout is especially high in train US (222) and France test (246).

## Error analysis

1. **India is the clearest warning.** Legal-form suffixes occur on roughly 84% of Source-1 names, yet about half of affected rows collapse onto a base shared by another distinct normalized Source-1 name. Private Limited alone has about 41% collision exposure.
2. **France is not a free unseen-country win.** SARL/SAS are extremely common, but individually each still puts about 29% of affected rows into newly merged bases; the full French core raises this to about 45%.
3. **US major forms are safer but still not clean.** LLC and Inc individually create about 18–22% collision exposure, and their combined train treatment reaches about 30%.
4. **Cross-form merging compounds the damage.** Core bundles lose 10–16% of unique normalized keys in the population slices, substantially more than the single-suffix variants.
5. **Fanout is bounded but nontrivial.** No Source-1 key passes 1,000, yet many affected rows acquire dozens to hundreds of additional same-key neighbors. A blocker can survive this computationally while still feeding the matcher worse negatives.

## Interpretation

The evidence rejects legal-form stripping as an unconditional replacement for the current normalized-name key. Its coverage is huge, especially in India and France, but the stripped key is too non-selective to treat as equivalent evidence.

The more defensible use is additive and gated: retain the original legal-form-bearing name, optionally add a stripped retrieval probe only when another independent signal is selective, such as address-number agreement, a rare token, or a low-frequency locality/address key. The suffix itself should remain available as matcher/provenance evidence rather than being erased globally.

This result also helps explain why character retrieval is attractive: it can gain robustness to suffix variation without forcing every corporate-form variant onto one exact lexical key.

## Risks

- Source-1 collision pressure is a proxy for Source-2/Source-3 posting pressure. The target inventories are unavailable in this runtime because the raw files exceed the connector transfer cap, so this experiment does not measure marginal pair recall or target candidate counts.
- The Python normalizer mirrors the semantics in src/ber/data.py using stdlib Unicode decomposition; the DuckDB runtime was unavailable here for byte-for-byte macro parity testing.
- The suffix list is conservative but hand-selected from high-frequency endings observed in supplied data. This is a forensic design decision, not a learned classifier.
- No official macro F0.5 is claimed. INT003 remains the model baseline.

## Recommendation

**REJECT** unconditional legal-form suffix stripping as a production replacement key.

**FOLLOW-UP** only as a bounded additive retrieval channel gated by independent selective evidence, with exact target-source candidate counts and marginal-positive recall measured in a runtime that can access full Source-2/Source-3 inventories. Priority should be India and France because coverage is highest and collision pressure is worst.

## Follow-up task

A useful next experiment is a target-side additive key of the form “stripped legal-form name + selective address/number evidence,” evaluated at fixed cap against INT003 retrieval. Do not test bare stripped-name union first; this audit already says its candidate pressure is likely poor.
