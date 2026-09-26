# M003 — Rare-number commonness features for current INT003 matcher

## Recommendation

**FOLLOW-UP.** The opt-in matcher primitive is implemented and the recovered branch was corrected so target numeric document frequency is country- and **target-source-local (S2 vs S3)** rather than pooled across both target sources. The default INT003/V3 57-feature path remains unchanged.

A full official macro-F0.5 ablation is not claimed in this chat because the live Drive connector rejects the required complete target files above its 256 MiB transfer ceiling. In this runtime, `train_source2.tsv` is 489,301,488 bytes and `train_source3.tsv` is 503,705,637 bytes. No sample or proxy score was substituted.

## Hypothesis

Current INT003 has number overlap/conflict indicators but does not distinguish agreement on a corpus-common number from agreement on a rare/distinctive number. Eight additive features based on minimum numeric-token document frequency may improve matcher precision/recall, especially for India, while leaving candidate generation fixed.

## Change

The branch adds:

- `src/ber/number_commonness.py`
  - extracts maximal ASCII digit runs with `[0-9]+`;
  - deduplicates numeric tokens per record before DF counting;
  - Source-1 DF is keyed by split + country + field;
  - target DF is keyed by split + country + **target source** + field;
  - normalized-value profile tables expose ordered token/DF lists for pair scoring;
  - eight features are appended: left/right shared-number log-DF and left/right unmatched-number log-DF for name and address.
- `src/ber/v4.py`
  - preserves V3 as an exact prefix and appends the eight M003 features;
  - reuses the same INT003 fused cap-160 candidate family.
- `src/ber/predict.py`
  - adds opt-in feature-version 4 inference support.
- `tests/test_number_commonness.py`
  - covers rarity/commonness semantics, empty/disjoint values, repeated-number deduplication, split validation, schema ordering, and target-source-local SQL/profile joins.

No production default, candidate generator, threshold, label use, or INT003 schema changes.

## Recovery audit

The abandoned branch was 4 commits ahead of current main with no PR or issue checkpoint after more than three hours. It was recovered rather than restarted.

The initial implementation pooled all target records with `s.source>1` when computing right-side DF. That violates the task's source-local requirement and can make a number common in S2 suppress/distort its evidence in S3, or vice versa. This recovery changed the right-side tables to group and join on `country, source, token` / `country, source, value`.

This correction is also consistent with the completed F003a full-Source-1 census, which recommends country/source/field-aware numeric DF rather than universal number evidence. F003a found that typical numeric collision burden differs sharply by country, with India and especially France exposing much more common address-number evidence than US records.

## Protocol

### Static / semantic validation

Repository branch:

`agent/m/M003-rare-number-commonness`

Relevant code commits:
- source-local correction: `63b8d2effd959bcfc438a639b09f072fb6c2e53e`
- focused test update: `03562e17cb48871b78a7af8dd17bb08599d3928e`

A dependency-light mirror of the branch semantics was executed in the available container because DuckDB is not installed there. Checks covered:

1. rare shared/unmatched numeric-token behavior;
2. empty/disjoint finite behavior;
3. repeated-token deduplication;
4. left country-local vs right country+source-local SQL grouping;
5. right profile joins pinned to the actual candidate source;
6. invalid split fail-closed behavior.

Result: **6/6 PASS**.

The container has NumPy but no DuckDB. Therefore no claim is made that the repository's DuckDB integration test suite ran in this environment.

### Data / full-score gate

Shared Drive access was verified. The training folder reports:

- `train_source1.tsv`: 210,069,713 bytes
- `train_ground_truth.tsv`: 127,015,583 bytes
- `train_source2.tsv`: 489,301,488 bytes
- `train_source3.tsv`: 503,705,637 bytes

Attempting a streamed raw fetch of `train_source2.tsv` fails before invocation with HTTP 413 because 489,301,488 bytes exceeds the connector's 268,435,456-byte limit. Since M003 needs target text and target-source-local DF, the full INT003 candidate/model ablation cannot be reproduced honestly in this chat runtime.

## Results

| Item | Baseline | M003 recovery |
|---|---|---|
| Default INT003 feature schema | 57 V3 features | unchanged |
| Opt-in feature schema | none | V3 + 8 numeric-commonness features |
| Candidate generator | INT003 fused cap160 | unchanged |
| Left numeric DF scope | n/a | split + country + field |
| Right numeric DF scope | pooled S2/S3 in abandoned draft | split + country + **target source** + field |
| Per-record repeated numbers | n/a | deduplicated before DF |
| Dependency-light semantic checks | n/a | 6/6 PASS |
| Official macro F0.5 | not run | **not run / not claimed** |

Candidate recall and blocking oracle are structurally unchanged by this matcher-only primitive, provided the exact same fused candidate cache is used in the eventual integration run.

## Error analysis

- **Cross-source contamination:** fixed. A number frequent in S2 but rare in S3 must not inherit pooled target commonness.
- **Repeated numeric runs:** handled by per-record deduplication, important because F003a observed materially more repeated numeric tokens in India.
- **Missing/empty numeric evidence:** encoded as zero commonness features; existing V3 overlap/conflict features provide the missing-vs-agreement context.
- **Country shift:** raw DF magnitudes can differ across US/India/France inventory sizes and number regimes. This is why the empirical gate must include India/US slices and France-safe transfer analysis before promotion.
- **Number semantics:** digit runs mix house/unit values, postcodes, years, phone-like strings, and identifiers. M003 deliberately learns from corpus frequency rather than hard-coding semantic types.

## Risks

1. No full candidate/model ablation was possible here because complete S2/S3 files exceed the live connector transfer limit.
2. Raw log-DF is an empirical feature, not a calibrated probability or IDF. CatBoost must demonstrate that it uses it beneficially.
3. Test-time DF is corpus-derived from supplied challenge records, consistent with the current V2/V3 frequency-feature pattern, but train/inference parity must still be verified on the private full-data runtime.
4. France has no labels. No French score, pseudo-label, or identity claim is made.
5. This branch should not replace INT003 unless the same-candidate integration gate improves official macro F0.5 robustly.

## Required integration gate

Run on the private/Modal full-data environment using the exact INT003 fused cap160 candidates and the same 108,115 fit anchors:

1. materialize V3 and V4 features on identical fit/early/calibration/holdout anchors;
2. train the same depth-10 CatBoost recipe;
3. recalibrate threshold only on the designated calibration fold;
4. report official macro F0.5, India, US, singleton FPR, threshold, runtime, and paired anchor deltas;
5. verify candidate recall/oracle are identical;
6. inspect whether gains concentrate on rare-number agreement/conflict buckets;
7. replicate any tiny gain before promotion.

Do not consume a new frozen confirmation window unless the coordinator promotes M003 to an integration candidate.
