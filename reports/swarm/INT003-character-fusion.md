# INT003 — bounded lexical and character retrieval

## Hypothesis

Rare name character 3/4-grams recover true links lost to spelling and spacing changes without requiring a large candidate cap. A matcher fitted on the resulting pool can use each retrieval channel as evidence.

## Change

`src/ber/retrieval_v3.py` fuses the existing lexical top 160 and a character-name top 64 by reciprocal rank, then keeps at most 160 unique candidates per Source 1 entity. It uses an average rank for equal retrieval scores. The RRF weight therefore depends on retrieval evidence, not the entity ID used to break final hard-cap ties. The v3 pair query exposes four channel scores/counts beyond the 53 v2 features. The Modal pipeline builds both train and test character indexes and uses separate v3 feature/model/output directories.

## Protocol

The retrieval gate compares both retrievers on the same 4,389 calibration entities against the **complete** training Source 2/3 inventory. Labels are read only to evaluate retrieved candidates. Cap 160 is fixed. The selected training population contains original development fit anchors plus fit-fold anchors from hash positions 50,001–200,000. Positions 45,001–50,000 are reserved for one frozen matcher confirmation after model selection.

Commands:

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
modal run -d modal_v3.py --action prepare
modal run -d modal_v3.py --action retrieval
modal run -d modal_v3.py --action train --depth 10
modal run -d modal_v3.py --action confirm --depth 10
```

## Retrieval results

| Same 4,389 anchors | Lexical v2 | Fusion v3 | Change |
|---|---:|---:|---:|
| Candidate pair recall | 0.925308 | 0.944357 | +0.019049 |
| Blocking-oracle macro F0.5 | 0.973081 | 0.980461 | +0.007380 |
| India oracle | 0.959832 | 0.969196 | +0.009364 |
| US oracle | 0.981900 | 0.987959 | +0.006060 |
| Mean candidates per anchor | 142.18 | 148.05 | +5.87 |
| Maximum candidates per anchor | 160 | 160 | 0 |

This is a **retrieval ceiling**, not a trained-model score. The mean candidate increase is about 4.1%; the real matching gain must justify it because candidate-set size matters in final ranking. The v3 ceiling is still below the team's 0.998 aspiration on this measured distribution, so further retrieval work is needed regardless of matcher quality.

## Matcher training

The 57-feature CatBoost depth-10 model used 108,115 fit anchors and 16,043,969 fitted candidate pairs. Its L4 fit and evaluation took 396 seconds; early stopping retained 1,793 trees. The calibration-only chosen threshold is 0.625, with a fairly flat 0.600–0.675 neighborhood. It scored 0.949121 on the 4,389-anchor calibration sample and 0.944783 on the reused 3,051-anchor development holdout. India scored 0.931688 / 0.917541 on those samples. These development scores are not independent confirmation and do not estimate France.

Frozen model SHA256: `9e25404658ae5fd0723d4beda55766c40f45b69d33ecf3f039d250994f4d73b9`. The model and fit arrays are private under `team517-business-er/project/experiments/int003/` and excluded from Git.

## Risks and next decision

France appears in test but has no training labels, so the US/India comparison cannot establish French performance. Equal-score candidates at a hard cap still need a deterministic tie break, currently entity ID; no ID enters any numeric model feature. The fused character index increases the private DuckDB from 8.86 GB to 16.71 GB. See `reports/int003_retrieval.json` and `reports/int003_database.json` for machine-readable aggregates.

## Frozen matcher confirmation

Positions 45,001–50,000 were evaluated once, after the model and threshold had been fixed. The baseline is the actual depth-10 v2 model with its original lexical candidate pool and threshold 0.65, evaluated on the **same** 5,000 anchors. The v3 model uses fused candidates and threshold 0.625.

| Same 5,000 anchors | V2 pipeline | V3 pipeline | Gain |
|---|---:|---:|---:|
| Macro F0.5 | 0.942285 | 0.950198 | +0.007914 |
| India macro F0.5 | 0.922066 | 0.932699 | +0.010633 |
| US macro F0.5 | 0.956013 | 0.962081 | +0.006067 |
| Pair recall | 0.923182 | 0.944065 | +0.020883 |
| Oracle macro F0.5 | 0.972929 | 0.980917 | +0.007988 |
| Singleton false-positive rate | 4.58% | 4.96% | +0.38 pp |

The paired entity-level gain is 0.007914; a 2,000-resample bootstrap (seed 517) gives a 95% interval of [0.005892, 0.009956]. V3 improves 403 entities and regresses 121. The India singleton slice regresses from 6/114 to 8/114 false positives, even though India's overall macro score improves by 0.010633. US singleton false positives improve from 6/148 to 5/148. See `reports/int003_depth10_confirmation.json`.

## Error analysis and interpretation

The retrieval channel recovers substantially more true pairs at the same hard cap, especially in India, and retraining on its actual candidate distribution converts this into a confirmed end-to-end gain. The v2 model scored only 0.932394 on the fused calibration pool versus the v3 model's 0.949121, so simply changing the blocker without retraining would have failed. Candidate misses still impose a 0.980917 oracle on confirmation, and matcher decisions leave another 0.030718 score points below that ceiling. These are different failure sources; a larger pair model alone cannot close the candidate gap.

## Recommendation and follow-up

**PROMOTE v3** for the next submission after full test export and format validation. Preserve the v2 file and checkpoint. Next retrieval work should target remaining India misses and France transfer with reverse retrieval, mixed name/address character channels, and a licensed multilingual encoder, each measured against complete target inventory at an auditable small cap. Next matcher work should target ambiguity and singleton false merges among retrieved pairs. Do not use this confirmation window for tuning.
