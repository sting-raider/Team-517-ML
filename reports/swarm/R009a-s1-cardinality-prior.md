# R009a — Source-1-only high-cardinality prior for adaptive candidate budgets

## Hypothesis

Inference-safe Source-1 record properties may identify anchors with unusually large true match sets. If so, retrieval could spend wider candidate budgets on those anchors instead of applying one global cap. The primary target is truth cardinality at least 5, because this is common enough to matter but represents materially higher recall pressure.

## Change

This experiment adds an analysis helper, src/ber/s1_cardinality_prior.py, and focused tests. It uses only Source-1 business name/address text plus corpus-frequency statistics computed from Source 1. Country is used only for evaluation slices. Entity IDs are used only for the repository's deterministic fold assignment and never enter the predictor.

The 24 primary features are raw/normalized name and address lengths, token counts, digit and numeric-token counts, non-ASCII and punctuation counts, whitespace counts, normalization-retention ratios, missingness, normalized name/address frequencies, and log-frequency transforms.

No retrieval, matcher, threshold, or submission behavior is changed.

## Protocol

Data:
- Complete train_source1.tsv: 210,069,713 bytes, 2,206,821 anchors.
- Complete train_ground_truth.tsv: 127,015,583 bytes, one truth row per anchor.
- No Source-2/Source-3 text, no external data, no confirmation/frozen holdout.
- High-cardinality target: |T| >= 5.
- Positive target count: 574,249 / 2,206,821 = 26.0215%.

Split:
- Exact fold517 protocol from src/ber/experiment.py.
- fit: 1,323,457
- early: 330,681
- calibrate: 331,219
- holdout: 221,464

Primary classifier:
- CatBoostClassifier, 100 trees, depth 7, learning rate 0.08, Logloss, seed 517.
- Hyperparameters were fixed before inspecting holdout results.
- Country excluded as a predictor.

Secondary regression:
- CatBoostRegressor, 100 trees, depth 7, learning rate 0.08, RMSE, seed 517.
- Predicts total truth cardinality 0–11.
- Compared with fit-set mean for RMSE and fit-set median for MAE.

Red-team checks:
1. A larger classifier: 200 trees, depth 8.
2. A normalization-independent raw-text-only classifier using raw lengths, digit/non-ASCII/punctuation/whitespace counts, missingness, raw exact name/address frequencies and log frequencies.
3. US and India holdout slices separately.
4. Budget-targeting lift at several selection fractions rather than relying only on AUROC.

Analysis runtime versions: CatBoost 1.2.8, pandas 2.2.3, NumPy 2.3.5. The repository pins CatBoost 1.2.10, so the patch-version difference is recorded as a reproducibility risk.

Reproduction helper:

    PYTHONPATH=src python -m ber.s1_cardinality_prior \
      --source1 /path/to/train_source1.tsv \
      --truth /path/to/train_ground_truth.tsv \
      --out /tmp/r009a.json \
      --strong-check --raw-check

Focused tests:

    PYTHONPATH=src python -m unittest tests/test_s1_cardinality_prior.py -v

The five focused tests pass. In this ChatGPT container, a fresh standalone full helper invocation exceeded the 180-second command cap while recomputing normalization and corpus frequencies. The empirical run itself was completed in staged full-data analysis. Measured full-data compute stages totaled about 158 seconds excluding initial CSV load/join: normalization 27.8 s, feature construction 35.6 s, primary classifier 20.1 s, regression 10.6 s, stronger classifier 31.1 s, and raw-only check 32.7 s. No runtime is inferred from the capped standalone invocation.

## Results

### Primary high-cardinality classifier

| Slice | N | Prevalence | AUROC | AUPRC |
|---|---:|---:|---:|---:|
| fit | 1,323,457 | 0.260355 | 0.514750 | 0.273232 |
| early | 330,681 | 0.260218 | 0.500228 | 0.260700 |
| calibrate | 331,219 | 0.260516 | 0.501242 | 0.261631 |
| holdout | 221,464 | 0.258931 | **0.500302** | **0.258865** |
| holdout US | 132,884 | 0.259467 | **0.502383** | **0.259991** |
| holdout India | 88,580 | 0.258128 | **0.498668** | **0.258114** |

Holdout AUPRC is slightly below prevalence. Holdout Brier is 0.191892 versus 0.191886 for a constant holdout prior; log loss is 0.571953 versus 0.571936 for the constant prior. In other words, the model does not merely fail to rank high-cardinality anchors; its probability quality is not better than a constant rate.

The fit AUROC of 0.51475 collapsing to about 0.50 on every non-fit split is consistent with weak memorization rather than transferable signal.

### Does the ranking help allocate budget?

On the untouched holdout:

| Fraction receiving extra budget | High-cardinality recall captured | Precision | Lift vs prevalence |
|---:|---:|---:|---:|
| 1% | 0.9766% | 25.282% | 0.976x |
| 2.5% | 2.5234% | 26.133% | 1.009x |
| 5% | 4.9874% | 25.829% | 0.998x |
| 10% | **9.9295%** | 25.711% | **0.993x** |
| 20% | 20.0003% | 25.893% | 1.000x |
| 30% | 29.8235% | 25.741% | 0.994x |
| 40% | 40.1001% | 25.958% | 1.002x |

A useful adaptive-cap prior should capture more than its random budget share. This one does not.

### Cardinality regression

On holdout:
- MAE: 1.370801
- Median-baseline MAE: 1.351755
- RMSE: 1.704770
- Mean-baseline RMSE: 1.704767
- Spearman rank correlation: **0.005276**

US Spearman is 0.00840 and India Spearman is 0.00083. The regressor is effectively a noisy constant predictor and is worse than the trivial baseline on MAE.

### Red-team checks

The larger 200-tree depth-8 classifier does not rescue the idea:
- holdout AUROC: **0.502641**
- holdout AUPRC: **0.260224**
- approximate AUROC SE: 0.001402
- approximate 95% interval: **[0.499894, 0.505388]**
- top 10% receives 10.0045% of high-cardinality anchors, lift 1.0005x

The raw-only model, which removes dependence on normalization parity, also remains essentially random:
- holdout AUROC: **0.502776**
- holdout AUPRC: **0.260097**
- holdout Brier: 0.191884
- holdout log loss: 0.571931

This is consistent with the separate D001a result that Source-1-only features also fail to predict true singleton status.

## Error analysis

1. **No useful tail exists.** The highest predicted risk deciles do not concentrate high-cardinality anchors. Even the stronger model's top 10% is indistinguishable from random targeting.
2. **No India-specific rescue.** India is slightly below random on the primary classifier, while US is only trivially above it. Country-specific Source-1 shape is not the missing signal.
3. **Frequency/collision features do not transfer.** The primary model can find weak fit-set quirks but they disappear on early/calibration/holdout.
4. **Exact set size is also unpredictable.** Regression rank correlation is approximately zero, so the failure is broader than the chosen |T| >= 5 cutoff.
5. **Normalizer choice is not the explanation.** A raw-only model reaches the same near-chance result.

## Interpretation

The number of Source-2/Source-3 records linked to an anchor is not meaningfully encoded in the anchor's Source-1 name/address shape or Source-1 collision frequency. This is plausible if duplicate/multiplicity generation is primarily a property of the target sources rather than of the reference record.

Therefore, adaptive retrieval budgets should not be driven by an S1-only learned cardinality prior. The useful signals are more likely to exist after retrieval: posting-list fanout, candidate count/saturation, score distribution and gaps, retriever-channel agreement, source balance, and other candidate-side ambiguity evidence.

This negative result is valuable because it rules out a cheap but tempting R009 shortcut before anyone tunes it against the confirmation set.

## Risks / red-team checks

- ID leakage: PASS. IDs only determine folds.
- Label leakage into features: PASS. Truth labels define targets only; corpus frequencies use Source-1 text without labels.
- Country leakage: PASS. Country is evaluation-only.
- Split contamination: PASS. Exact fold517 split counts reproduce prior full-data audits.
- Sampling mismatch: PASS. Full Source-1 and full ground truth used.
- Confirmation reuse: PASS. No confirmation/frozen window used.
- Normalization parity: minor risk for the 24-feature primary model because the chat runtime lacks DuckDB 1.5.5 and used NFKD combining-mark removal rather than DuckDB strip_accents. The raw-only check removes this dependency and reaches the same null conclusion.
- CatBoost patch version: runtime 1.2.8 versus repository pin 1.2.10. The effect size is so close to random, and the stronger model/raw-only checks agree, so a patch-level reversal large enough to make this useful is implausible but should not be claimed impossible.
- No end-to-end macro F0.5 delta is claimed because this runtime cannot materialize complete S2/S3 text and therefore cannot legally construct the target-side candidate pool.

## Recommendation

**REJECT** Source-1-only cardinality prediction as the basis for R009 adaptive candidate budgets.

Do not add these features to retrieval-budget logic. The evidence-backed next R009 experiment is candidate-side adaptive budgeting using actual blocker fanout/saturation and retriever evidence on the same fixed calibration anchors, with pair/entity/all-matches recall, blocking-oracle macro F0.5, candidate-count quantiles, country/source slices, and runtime.

## Follow-up

Once a worker has complete S2/S3 access (for example through the shared Modal volume), test adaptive caps based on inference-time retrieval ambiguity rather than predicted truth cardinality. R019's source-starvation findings should also be considered when defining any per-source floor or budget.
