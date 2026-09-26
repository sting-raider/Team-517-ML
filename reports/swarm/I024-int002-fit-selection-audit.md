# I024 — INT002 expanded fit-population selection audit

**Issue:** #187  
**Branch:** `agent/i/I024-int002-fit-selection-audit`  
**Recommendation:** **PROMOTE** the current INT002 fit-selection protocol as internally consistent and compositionally representative on the audited axes.

## Hypothesis

INT002 expands fitting beyond the original 30,000-anchor development population. The actual CatBoost fit set should contain the documented 108,115 anchors, exclude all consumed development evaluation / confirmation regions, and not acquire a material country or truth-cardinality skew from the 50k–200k expansion.

## Change

No model or data-selection behavior was changed. This is an independent full-population reconstruction of the exact latest-main selection logic in `src/ber/v2.py` and `src/ber/experiment.py`.

## Protocol

Complete supplied files:

- `train_source1.tsv`: **2,206,821** anchors.
- `train_ground_truth.tsv`: **2,206,821** truth rows.

Exact sample ordering:

```text
md5("sample517:" + entity_id)
```

Exact fold assignment:

```text
bucket = int(sha256("fold517:" + entity_id)[:8], 16) % 100
fit       if bucket < 60
early     if 60 <= bucket < 75
calibrate if 75 <= bucket < 90
holdout   otherwise
```

Latest-main `v2.select_anchors` materializes:
- all positions <=30,000 with their normal fold labels;
- only `fit` anchors from positions 50,001–200,000;
- positions 30,001–50,000 are excluded from fitting;
- confirmation mode separately selects positions 40,001–45,000.

The model trainer then fits only anchors labeled `fit`.

No S2/S3 data, candidates, probabilities, model weights, new holdout rows, threshold tuning, or leaderboard feedback were used.

## Results

### Exact selection parity

The reconstructed INT002 fitting population is exactly **108,115 anchors**, matching the committed model configuration and submission report:

- original development fit anchors, positions 1–30,000: **17,990**
- expanded fit anchors, positions 50,001–200,000: **90,125**
- total fit anchors: **108,115**

The reconstructed first-30k development fold counts are also exactly:

| Fold | Anchors |
|---|---:|
| fit | 17,990 |
| early | 4,570 |
| calibrate | 4,389 |
| holdout | 3,051 |

Integrity checks:

- fit anchors in positions 30,001–50,000: **0**
- fit anchors in INT002 confirmation positions 40,001–45,000: **0**
- therefore the current 5,000-anchor confirmation block is structurally excluded from INT002 fitting.

### Composition

| Metric | Full train population | INT002 fit anchors | Difference |
|---|---:|---:|---:|
| Anchors | 2,206,821 | 108,115 | — |
| India share | 40.0208% | 39.9205% | **-0.1004 pp** |
| Singleton rate | 5.5848% | 5.5219% | **-0.0629 pp** |
| Mean truth cardinality | 3.461253 | 3.462665 | +0.001412 |
| US singleton rate | 5.5828% | 5.6531% | +0.0703 pp |
| India singleton rate | 5.5878% | 5.3244% | -0.2635 pp |

The mean-cardinality standardized mean difference is only **0.00083**.

Under a pseudo-random hash-sampling reference:
- India-share deviation: **z = -0.674**
- singleton-rate deviation: **z = -0.901**
- mean-cardinality deviation: **z = +0.272**

The fit population contains **43,160 India anchors** versus about **43,268.5 expected** at the full-population country share, and **5,970 singletons** versus about **6,038.0 expected**.

Truth-cardinality category differences are tiny:

| Matches | Fit minus population |
|---|---:|
| 0 | -0.0629 pp |
| 1 | +0.0836 pp |
| 2 | -0.0538 pp |
| 3 | +0.0115 pp |
| 4 | +0.0431 pp |
| 5+ | -0.0215 pp |

No audited category differs by even 0.1 percentage point.

## Error analysis

1. **Training/confirmation overlap:** none. The entire 30k–50k exclusion band is absent from fitting, including the current confirmation block.
2. **Fold reconstruction:** exact parity with the known 17,990 / 4,570 / 4,389 / 3,051 development fold counts.
3. **Training-anchor count:** exact parity with INT002's committed `training_anchors=108115`.
4. **Country composition:** effectively unchanged from the full population.
5. **Singleton/cardinality composition:** effectively unchanged. The expanded training population does not inherit the India-singleton anomaly of the small 3,051-anchor development holdout.
6. **Target-side difficulty:** not audited. A compositionally representative Source-1/truth population can still differ in candidate hardness or S2/S3 corruption.

## Interpretation

The 50k–200k expansion did what it was supposed to do: add a much larger fit-only population without contaminating the predeclared development evaluation or current confirmation block.

There is no evidence that INT002's measured improvement is an artifact of a country/singleton/cardinality-skewed training selection. This does not validate every aspect of the model or its France transfer, but it removes one plausible integrity concern around the new 108k-anchor training regime.

## Risks

- S2/S3 candidate difficulty and target-side corruption were not measured because those files exceed this runtime's live Drive transfer ceiling.
- The audit validates selection and aggregate composition, not whether the additional fit anchors improve generalization causally.
- Full training labels are used only to compute aggregate truth cardinality, not to choose anchors or tune the model.
- France is absent from training labels; no French accuracy conclusion follows.

## Recommendation

**PROMOTE** the current INT002 fit-selection protocol as a sound basis for subsequent matched-pool retraining.

Keep these invariants:
- 30k–50k remains excluded from fitting;
- confirmation blocks remain predeclared and consumed after one integration decision;
- future training expansions should preserve fold517 and record exact fit-anchor counts;
- candidate/retrieval changes still need same-slice evaluation because Source-1 composition parity does not guarantee target-side parity.

## Follow-up tasks

When INT003/R024 retrains on the changed character-retrieval candidate distribution, it can safely reuse this anchor-selection regime; the scientific variable should remain the candidate pool rather than the anchor population.
