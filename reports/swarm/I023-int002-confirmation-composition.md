# I023 — INT002 40k–45k confirmation composition audit

**Issue:** #182  
**Branch:** `agent/i/I023-int002-confirmation-composition`  
**Recommendation:** **PROMOTE** the already-consumed INT002 confirmation window as compositionally sound on the audited Source-1 country and truth-cardinality axes.

## Hypothesis

The current INT002 headline result, macro F0.5 **0.940478**, was measured on hash positions 40,001–45,000. That block should resemble the complete training Source-1 population on country mix and truth cardinality/singleton structure. A material imbalance could make the India or singleton diagnostics look better or worse by chance.

## Change

No model, blocker, threshold, feature, or candidate change was made.

This task independently reconstructs the exact already-consumed INT002 confirmation block from complete supplied Source-1 and ground-truth files and compares its composition with the full training anchor population. It extends I020, which audited earlier 30k–35k and 35k–40k windows but did not audit the current 40k–45k block.

## Protocol

Complete supplied files from the shared Google Drive:

- `train_source1.tsv`: **2,206,821** anchors, 210,069,713 bytes.
- `train_ground_truth.tsv`: **2,206,821** rows, 127,015,583 bytes.

Exact latest-main selection semantics from `src/ber/v2.py`:

```sql
row_number() OVER(
  ORDER BY md5('sample517:' || entity_id)
) AS sample_position
...
sample_position > 40000 AND sample_position <= 45000
```

The empirical audit computed the complete MD5 ordering for all 2,206,821 Source-1 IDs, found **zero duplicate MD5 ordering keys**, selected exactly positions 40,001–45,000, joined ground truth one-to-one, and computed aggregate composition. No sample was substituted for population aggregates.

The complete empirical pass took about **24 seconds** in the chat Python runtime. The selected-window composition was cross-checked against `reports/int002_depth10_confirmation.json`.

No S2/S3 records, candidate lists, model probabilities, new/future holdout rows, threshold tuning, or leaderboard feedback were used.

## Results

### Exact reconstruction parity

The independently reconstructed 5,000-anchor block contains:

- **1,978 India** anchors.
- **3,022 US** anchors.
- **275 singletons**.
- India singletons: **113 / 1,978 = 5.7128%**.
- US singletons: **162 / 3,022 = 5.3607%**.

These counts exactly match the committed INT002 confirmation artifact, including the country entity counts and singleton counts. That is a strong end-to-end parity check on the hash-window reconstruction.

### Population vs INT002 confirmation

| Metric | Full train population | INT002 40k–45k | Difference |
|---|---:|---:|---:|
| Anchors | 2,206,821 | 5,000 | — |
| India share | 40.0208% | 39.5600% | **-0.4608 pp** |
| Singleton rate | 5.5848% | 5.5000% | **-0.0848 pp** |
| Mean truth cardinality | 3.4613 | 3.4764 | +0.0151 |
| US singleton rate | 5.5828% | 5.3607% | -0.2221 pp |
| India singleton rate | 5.5878% | 5.7128% | +0.1250 pp |

The mean-cardinality standardized mean difference is **0.0089**, which is tiny. Relative to pseudo-random sampling from the complete population, the mean-cardinality deviation is about **z = 0.63**.

The window contains **1,978 India anchors** versus about **2,001.0 expected** from the population share, and **275 singletons** versus about **279.2 expected**.

Descriptive z diagnostics:

| Quantity | z |
|---|---:|
| India share | -0.665 |
| Singleton rate | -0.261 |
| US singleton rate | -0.532 |
| India singleton rate | +0.242 |

None is remotely suggestive of a material composition anomaly.

### Truth-cardinality distribution

| Matches | Full population | INT002 40k–45k | Difference |
|---|---:|---:|---:|
| 0 | 5.5848% | 5.5000% | -0.0848 pp |
| 1 | 5.3995% | 5.2400% | -0.1595 pp |
| 2 | 17.0024% | 16.8200% | -0.1824 pp |
| 3 | 24.0546% | 24.1600% | +0.1054 pp |
| 4 | 21.9372% | 21.8600% | -0.0772 pp |
| 5+ | 26.0215% | 26.4200% | +0.3985 pp |

The largest audited category deviation is only **+0.3985 percentage points** for cardinality 5+ (descriptive z ≈ **0.64**).

Exact full-population cardinality counts were:

```text
0: 123,247
1: 119,157
2: 375,212
3: 530,841
4: 484,115
5: 321,957
6: 164,868
7: 63,968
8: 18,680
9: 4,205
10: 534
11: 37
```

The INT002 window counts were:

```text
0: 275
1: 262
2: 841
3: 1,208
4: 1,093
5: 766
6: 346
7: 147
8: 52
9: 9
10: 1
```

## Error analysis

1. **Country mix:** no material skew. India is underrepresented by only 23 anchors relative to population expectation.
2. **Singleton mix:** no material skew overall or within country. This sharply contrasts with the older 3,051-anchor development holdout identified by I020, where India singletons were accidentally overrepresented.
3. **Truth cardinality:** no material distortion. Every audited category is within 0.4 percentage points of population.
4. **Reconstruction integrity:** full Source-1 and ground-truth row counts match; IDs are one-to-one; exact MD5 ordering has no duplicate keys; selected country/singleton counts exactly reproduce the committed INT002 confirmation artifact.
5. **No causal score attribution:** this audit does not claim that composition explains or validates the model gain itself. It only rules out these obvious composition axes as a reason to distrust the confirmation sample.

## Interpretation

The current **0.940478** INT002 confirmation result does not appear to benefit from an unusually easy country/singleton/cardinality mix. The 40k–45k window looks like an ordinary pseudo-random slice of the full training Source-1 population on every audited dimension.

This strengthens the interpretation of the already-reported INT002 gain over the submitted-v1 model because the current confirmation block is not suffering the India-singleton composition anomaly seen in the small development holdout.

It does **not** prove representativeness for retrieval difficulty, S2/S3 corruption patterns, candidate density, matcher-score margins, address/name noise, or France. Those require target-side or prediction artifacts.

## Risks

- France is absent from training labels; this audit says nothing about French test accuracy.
- S2/S3 files are above the live Drive connector's 256 MiB transfer ceiling, so target-side corruption/retrieval difficulty was not audited here.
- Descriptive z values use the complete population proportion as the reference under pseudo-random hash sampling. They are diagnostics, not formal multiple-testing-adjusted inference.
- Full Source-1 research has inspected training labels globally, so this is a composition audit of an already-consumed confirmation block, not a claim of globally untouched data.

## Recommendation

**PROMOTE** the INT002 40k–45k confirmation block as a trustworthy composition check for the current matcher on the audited axes.

Operationally:
- keep positions 40,001–45,000 consumed and out of future tuning;
- continue to report India and singleton slices, but no special composition correction is warranted for this block;
- do not use the old 3,051-anchor development holdout alone to adjudicate tiny India/singleton gains;
- for the next integration candidate, use a newly predeclared confirmation block only after development selection is frozen.

## Follow-up tasks

A future evaluation-integrity pass can compare retrieval-difficulty and score-margin distributions across consumed windows if a compact candidate/prediction artifact is available, without rereading raw S2/S3.
