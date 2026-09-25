# X002 — Unicode/diacritic normalization ablation

**Issue:** #101  
**Pod:** X (France/generalization)  
**Branch:** `agent/x/X002-unicode-diacritic-ablation`  
**Recommendation:** **FOLLOW-UP**

## Hypothesis

The current folded-only text representation discards Unicode/diacritic distinctions that are substantially more common in unseen-France records. Keeping the existing accent-folded view for recall while adding a Unicode-preserving parallel view may provide extra discrimination with low transfer risk.

## Change

No production retrieval or matcher behavior changed. This recovery run completed the previously blocked full-Source-1 ablation and measures information loss caused specifically by accent folding.

The comparison is:

- **Unicode view:** lowercase, retain Unicode letters/numbers, collapse other runs to spaces.
- **Folded view:** remove canonical combining accents, then apply the same normalization.

The production normalizer remains:

```sql
trim(regexp_replace(lower(strip_accents(coalesce(s, ''))), '[^\\p{L}\\p{N}]+', ' ', 'g'))
```

DuckDB is unavailable in this chat runtime, so the empirical pass used the same NFD/combining-mark fallback previously used by X007. As a parity check, the full-file France changed rates exactly reproduce X007's aggregate rates.

## Protocol

Complete supplied Source-1 files, no sampling:

- `train_source1.tsv`: 2,206,821 anchors / 210,069,713 bytes
- `test_source1.tsv`: 1,732,544 anchors / 175,022,086 bytes
- train countries: US, India
- test countries: US, India, France
- France test anchors: 259,452

The run streamed the TSVs in deterministic 250k-row chunks, wrote only normalized key pairs to temporary local files, externally grouped them, and emitted aggregate counts. No raw rows, IDs, or text are committed.

For each split/country/field it measures:

- fraction of rows changed by accent folding,
- distinct-key loss,
- exact-key collision-row rate before vs after folding,
- folded groups containing multiple Unicode-preserving keys,
- rows that were unique under the Unicode view but become colliding after folding,
- additional within-key pair mass introduced by folding,
- row-weighted fanout quantiles.

Aggregate JSON: `reports/swarm/X002-unicode-diacritic-ablation.json`.

Measured normalization time across execution slices: 122.83 s. Aggregate grouping scan: 15.54 s. External-sort wall time was not separately instrumented.

## Results

### Full country/split control

| Slice | Field | rows changed by fold | collision-row inflation |
|---|---|---:|---:|
| train US | name | 0.0000% | +0.0000 pp |
| train US | address | 0.0000% | +0.0000 pp |
| train India | name | 0.0000% | +0.0000 pp |
| train India | address | 0.0627% | +0.0000 pp |
| test US | name | 0.0000% | +0.0000 pp |
| test US | address | 0.0000% | +0.0000 pp |
| test India | name | 0.0000% | +0.0000 pp |
| test India | address | 0.0574% | +0.0000 pp |
| test France | name | **15.7208%** | **+0.3126 pp** |
| test France | address | **27.8314%** | **+0.4182 pp** |

The important control is not merely that French text contains more diacritics. In the complete US/India Source-1 populations, accent folding causes **zero distinct-key loss and zero collision inflation**. The measured collision effect is France-specific in this dataset.

### France name keys

On all 259,452 French Source-1 anchors:

- 40,788 names (15.7208%) change under accent folding.
- distinct nonempty keys fall from 192,936 to 192,254: **682 distinctions lost**.
- exact-key collision-row rate rises from **34.0934%** to **34.4060%**, a **+0.3126 pp** increase.
- 678 folded name keys contain multiple Unicode-preserving variants.
- those affected folded groups contain 3,678 rows (1.4176% of France S1).
- 811 rows (0.3126%) are unique under the Unicode view but become colliding under folding.
- folding adds **7,080** within-key row pairs relative to the Unicode view.
- the largest affected folded key contains 3 Unicode variants.

Row-weighted fanout quantiles remain p50=1, p90=11, p99=71, p99.9=157 in both views. The accent effect is therefore localized rather than a global explosion in name-key fanout.

### France address keys

On the same 259,452 anchors:

- 72,209 addresses (27.8314%) change under accent folding.
- distinct nonempty keys fall from 241,408 to 240,815: **593 distinctions lost**.
- exact-key collision-row rate rises from **10.6875%** to **11.1057%**, a **+0.4182 pp** increase.
- 593 folded address keys contain multiple Unicode-preserving variants.
- those groups contain 1,380 rows (0.5319% of France S1).
- 1,085 rows (0.4182%) are unique under the Unicode view but become colliding under folding.
- folding adds **798** within-key row pairs.
- every affected folded address key has two Unicode variants.

Row-weighted address fanout quantiles remain p50=1, p90=2, p99=9, p99.9=86 in both views.

## Interpretation

This is stronger evidence than the prior “France has accents” census: the folded representation demonstrably removes distinctions and creates extra exact-key ambiguity on French Source-1 records, while the same effect is absent from the US/India controls.

It does **not** establish that accent folding is bad overall. Folding can recover genuine variants, and the present blocker/matcher were trained around that behavior. Replacing it would risk recall. The evidence supports a **parallel Unicode-preserving view** as complementary evidence, not a swap.

The effect is also narrow. Global fanout quantiles do not move, and only about 0.3–0.4% of French rows become newly colliding from accent folding. This is unlikely, by itself, to bridge the current retrieval-oracle gap. It is nevertheless one of the few measured France-specific representation losses available without inventing labels.

## Baseline / metric boundary

Current selected end-to-end reference remains:

- confirmation macro F0.5: 0.928835
- cap-640 pair recall: 0.947246
- blocking oracle macro F0.5: 0.980951

Those metrics are **not re-evaluated here** because complete S2/S3 files exceed the live Drive connector's raw transfer ceiling and France has no labels.

For this exact S1 ablation, the baseline is the current folded representation on the same rows; the Unicode view reduces French exact-key collision rate by 0.3126 pp for names and 0.4182 pp for addresses.

## Red-team / integrity

- Complete S1 train/test populations were processed; no feasibility sample was substituted.
- Country row totals reproduce repository counts exactly.
- France fold-change rates exactly reproduce the independent X007 full-file census.
- US/India are retained as controls and show zero collision inflation.
- No IDs are used as predictive features.
- No ground-truth labels, confirmation anchors, frozen holdout, or leaderboard feedback were used.
- No external business/entity data or French pseudo-labels were used.
- The NFD fallback is a semantic mirror, not a byte-for-byte DuckDB `strip_accents` proof; exact production integration must rerun with DuckDB.
- S1 exact-key fanout is a format/discrimination diagnostic, not production S2/S3 blocker frequency and not candidate recall.

## Recommendation

**FOLLOW-UP.**

Do not replace accent folding. The next decisive experiment should retain the folded baseline and add a Unicode-preserving name/address channel to retrieval and/or pair features, then benchmark on identical labeled US/India development anchors with:

- official macro F0.5,
- pair/entity/all-matches retrieval recall,
- blocking oracle,
- candidate-count quantiles,
- US/India and transfer-stress slices,
- identical cap and threshold protocol.

For France, use only unlabeled candidate-density/key-survival diagnostics until legal labels exist.