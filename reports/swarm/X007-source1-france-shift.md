# X007 — Full Source-1 France normalization / format-shift audit

**Issue:** #14  
**Pod:** X (France / generalization)  
**Branch:** `agent/x/X007-source1-france-shift`  
**Recommendation:** **FOLLOW-UP**

## Hypothesis

French Source-1 records may differ enough from labeled US/India records that the current lexical normalization and blocking assumptions lose useful evidence before the matcher sees a pair. The goal here is to quantify that shift on the complete accessible Source-1 inventory, without inventing France labels or using external business data.

## Change

No production matcher/blocker behavior was changed. Added a deterministic Source-1 distribution audit helper (`tools/audit_source1_shift.py`) that mirrors the current `src/ber/data.py` normalization and reports country-level text-shape metrics, normalization collisions, and a clearly-labeled Source-1-only token-frequency proxy.

## Protocol

Data came from the shared challenge Drive and was processed locally as raw TSV files:

- `train_source1.tsv`: 210,069,713 bytes, **2,206,821** anchors
- `test_source1.tsv`: 175,022,086 bytes, **1,732,544** anchors
- total audited: **3,939,365 Source-1 records**

Complete country counts matched the repository audit exactly:

| split | US | India | France | total |
|---|---:|---:|---:|---:|
| train | 1,323,633 | 883,188 | 0 | 2,206,821 |
| test | 663,106 | 809,986 | 259,452 | 1,732,544 |

The ChatGPT execution environment did not have the repo-pinned `duckdb` package installed and has no package-network access. The empirical pass therefore used chunked pandas string operations implementing the same documented transform: lowercase, Unicode NFD accent removal, replacement of non-letter/non-number runs with spaces, and whitespace trimming/collapse. The committed reproduction helper uses DuckDB's actual `strip_accents` / Unicode regex path from the repo. The helper was syntax-compiled in this runtime but could not be executed here because `duckdb` is absent.

The sandbox also kills long single executions, so both complete files were losslessly split into 250,000-line shards and all shards were reduced. No target-inventory sample was substituted. A representative 250k-row shard took **10.14 s** with **347,780 KB max RSS**; end-to-end wall time was not measured as one process because of the sandbox execution ceiling.

For the France token diagnostic, document frequency was computed on Source-1 only with the blocker's length/address-stopword rules and the same nominal `<=1000` threshold. This is explicitly a **proxy**, not the production blocker frequency, because real frequencies are measured on S2/S3.

No external business registry, geocoder, directory, web identity data, record IDs as predictors, labels, or French pseudo-labels were used.

## Results

### 1. US and India Source-1 formatting is almost stationary from train to test

Several independent format metrics barely move between train and test. Examples:

- US leading-number address rate: 85.975% train → 86.009% test (**+0.035 pp**)
- US 5-digit-token address rate: 10.949% → 10.945% (**-0.004 pp**)
- India leading-number address rate: 25.799% → 25.723% (**-0.076 pp**)
- India address hyphen rate: 38.587% → 38.740% (**+0.152 pp**)
- name normalization-change rate: US 26.650% → 26.555%; India 12.333% → 12.254%

That makes the France differences below much less likely to be generic train/test formatting drift.

### 2. France is a real orthographic / address-format shift

| metric (test S1) | US | India | France |
|---|---:|---:|---:|
| name average raw length | 22.46 | 26.37 | **19.42** |
| name normalized tokens p50 / p90 | 3 / 5 | 4 / 5 | **3 / 4** |
| name accent-fold changed | 0.000% | 0.000% | **15.721%** |
| name changed by full normalizer | 26.555% | 12.254% | **29.245%** |
| address average raw length | 34.97 | 77.71 | **50.07** |
| address normalized tokens p50 / p90 | 6 / 8 | 12 / 17 | **8 / 11** |
| address non-ASCII | 0.000% | 0.057% | **28.265%** |
| address accent-fold changed | 0.000% | 0.057% | **27.831%** |
| address contains hyphen-like punctuation | 1.132% | 38.740% | **82.819%** |
| address begins with a number | 86.009% | 25.723% | **86.010%** |
| address contains a standalone 5-digit token | 10.945% | 0.281% | **0.413%** |

France is therefore not simply “India-like” or “US-like.” Its address length sits between the two, but its hyphen/accent behavior is far outside both labeled countries.

A positive transfer signal is also visible: **86.010%** of French addresses begin with a number, effectively identical to US test (**86.009%**). The blocker's number+token evidence is therefore not obviously mismatched to French Source-1 format.

### 3. Accent folding removes measurable information, but Source-1 alone does not show that it is net harmful

On all 259,452 French anchors:

- business-name accent folding maps multiple distinct lowercased raw strings onto the same folded key for **1.418% of rows**; full current normalization collision keys cover **1.536% of rows**.
- address accent folding collision keys cover **0.503% of rows**; full normalization collision keys cover **0.829% of rows**.
- French address distinct lowercased strings fall from 241,611 raw forms to 240,815 normalized forms, a loss of 796 distinct forms.

For context, full-normalization collision-row rates on test Source-1 are:

| field | US | India | France |
|---|---:|---:|---:|
| business name | 7.613% | 1.583% | **1.536%** |
| business address | 0.000% | 0.101% | **0.829%** |

So France is **not uniquely collision-prone in names**; US name normalization collapses more forms. France *is* notably more collision-prone in addresses than either labeled country. Because both sides of a true pair are normalized with the same function, this audit does **not** prove that accent stripping lowers recall or F0.5. It does justify testing a raw-Unicode view in parallel rather than assuming folded-only text is harmless.

### 4. France name evidence has weaker rare-token redundancy, not a catastrophic absence of rare tokens

The most frequent normalized French Source-1 name tokens include:

- `sarl` 73,486
- `sas` 52,278
- `club` 22,672
- `france` 20,793
- `eurl` 16,980
- `ecole` 15,668
- `amicale` 14,389
- `comite` 13,832

Seven very frequent terminal tokens (`sarl`, `sas`, `eurl`, `sa`, `sasu`, `sci`, `ei`) terminate **178,751 / 259,452 = 68.896%** of French Source-1 business names. This is an observed challenge-data pattern, not an externally supplied lexicon.

Using Source-1 document frequency `<=1000` only as a proxy for the production blocker threshold:

| proxy metric | US test names | France test names |
|---|---:|---:|
| zero rare eligible tokens | 22.781% | **20.147%** |
| at least 1 rare token | 77.219% | **79.853%** |
| at least 2 rare tokens | 40.290% | **8.477%** |
| mean rare tokens / name | 1.293 | **0.887** |

This rejects the simplistic hypothesis that French names usually have *no* discriminative token. The stronger signal is **low redundancy**: French names much less often have two independent rare tokens. A corruption/deletion of the one distinctive token can therefore be more damaging to token blocking.

The same Source-1 proxy for French addresses is healthier: 97.378% have at least one rare eligible address token and 30.344% have at least two. Again, this is not S2/S3 candidate recall and must not be presented as such.

### 5. The current English-oriented address stoplist is visibly incomplete for France, but the existing frequency cutoff may already neutralize the worst terms

The highest-DF French address tokens are `rue` (170,769), `france` (101,838), `hauts` (101,712), `nouvelle` (85,303), `aquitaine` (85,214), `pays` (72,780), and `loire` (72,764). None are in the current `address_words()` stoplist.

However, blocker v2 drops target keys with frequency >1000. If S2/S3 frequencies resemble Source-1, these ultra-common keys would already be excluded. Adding French stopwords may reduce index construction work, but **this audit provides no evidence that a stoplist change would raise recall or F0.5**. Production S2/S3 frequency and candidate-density measurements are required first.

## Error analysis / interpretation

The main failure mechanisms suggested by Source-1 format are:

1. **Single-distinctive-token dependence in names.** France often has one rather than multiple rare name tokens. Token deletion/spelling noise can therefore erase all useful name-blocking evidence more easily.
2. **Folded-address information loss.** Accent + punctuation normalization merges more distinct French address forms than US/India addresses, although the absolute affected-row fraction remains below 1% for full address normalization.
3. **Heavy hyphenation is structural.** 82.819% of French addresses contain a hyphen-like character. The current normalizer splits it to spaces. That may help tokenization, but means raw character evidence can carry information absent from normalized features.
4. **Numeric structure transfers well.** France's leading-number rate matches US almost exactly, so the existing number+token mechanisms have a plausible transfer path.
5. **No evidence of broad Source-1 drift in labeled countries.** US/India train→test stability is unusually tight, strengthening confidence that the France shift is real rather than a global test-format change.

## Risks / limitations

- **No France labels.** None of these measurements is a French accuracy, recall, oracle, or F0.5 estimate.
- **Source-1 only.** S2/S3 raw TSVs exceed the live connector's 256 MiB download limit (roughly 489–509 MB each). Actual production posting-list frequencies, candidate counts, and missed true links were not measured here.
- **DF proxy is not blocker DF.** Production blocker frequencies are calculated on target records, not anchors. Source-1 `<=1000` statistics are only format diagnostics.
- **Normalizer implementation check.** Empirical execution used a semantic NFD mirror because DuckDB is absent from this sandbox. The committed helper uses the repo's actual DuckDB normalization for reproduction in the normal project environment.
- No threshold was tuned and no confirmation/frozen score was touched.

## Recommendation: FOLLOW-UP

Do **not** replace accent folding or add a France-specific stoplist based on this audit alone.

Highest-value next tests are:

1. **X002 / raw-Unicode parallel view:** keep the existing folded view, add raw-Unicode character/exact similarity or retrieval evidence in parallel, and evaluate on labeled US/India plus country-transfer stress. The mechanism is concrete: folded-only address normalization collapses 0.829% of French Source-1 rows onto collision keys, with 0.503% attributable to accent folding alone.
2. **France candidate-density audit once full S2/S3 access is available:** measure actual query-key survival by key kind, target posting-list frequencies, candidate-count distribution, and saturation for France without labels. This can verify whether the common French tokens are harmlessly filtered or leave anchors under-blocked.
3. **Complementary character-name retrieval:** prioritize robustness to loss/corruption of the single distinctive French-like name token. The existing R002 experiment is aligned with this mechanism, but it needs full target inventory / Modal execution before any score claim.

This audit raises a concrete France robustness concern while also ruling out a more dramatic claim: Source-1 evidence does **not** suggest that French records are generically unretrievable by the current lexical scheme.