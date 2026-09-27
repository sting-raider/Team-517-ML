# R030 — name-family-disjoint character prior for high-cardinality anchors

## Hypothesis

R009a rejected a Source-1-only high-cardinality prior built from shape, missingness, digit, and collision-frequency features, but its red-team scoped that null to the tested feature family. R030 asks whether the actual Source-1 business-name text, represented by language-agnostic character n-grams, contains transferable signal for anchors with truth cardinality |T| >= 5 that could justify adaptive retrieval budgets.

A second requirement is that any signal survive a name-family-disjoint split. A model that only learns that a repeated brand tends to have many Source-2/Source-3 records is not a safe general-purpose prior.

## Change

No production retrieval, matcher, threshold, or submission behavior changes.

The experiment adds tools/experiments/r030_char_cardinality_prior.py and focused tests. It reads complete supplied Source-1 + truth, reproduces the R009a target and exact fold517 split, builds a Unicode-preserving normalized business-name view, and adds a second split by hashing the normalized name family itself. Identical normalized name families therefore cannot cross fit/holdout.

The text model is character 3–4 gram HashingVectorizer plus a linear logistic SGD classifier. Entity IDs are used only for supplied-label joins and the established deterministic fold; they never enter the predictor. Country is evaluation-only.

## Protocol

Data:
- complete train_source1.tsv: 2,206,821 anchors;
- complete train_ground_truth.tsv: one truth row per anchor;
- no Source-2/Source-3 text;
- no external identity data;
- no confirmation/frozen holdout;
- no France labels or leaderboard feedback.

Full-population reconstruction:
- |T| >= 5 anchors: 574,249 / 2,206,821 = 26.021549%;
- mean truth cardinality: 3.461253; maximum 11;
- US anchors: 1,323,633; India: 883,188;
- exact fold517 fit: 1,323,457; holdout: 221,464;
- name-family fit: 1,321,318; holdout: 221,883;
- unique normalized name families: 1,520,684;
- exact family fit/holdout overlap: 0;
- ordinary entity-split holdout rows whose normalized name family appears in fit: 34.840877%.

The first attempted full sparse-text pass exceeded the execution wrapper ceiling before any model output. Per the pre-declared issue protocol, the classifier gate therefore uses a deterministic Tier-1 sample fallback after full-population census/split construction: 200,000 fit rows and 80,000 holdout rows per run, selected without labels. Independent seeds are 517 and 2026.

Model:
- Unicode-preserving normalized business_name only;
- HashingVectorizer, char_wb, n-grams 3–4, 131,072 features;
- averaged SGDClassifier with log-loss, alpha 1e-5;
- fixed hyperparameters before evaluation.

Red-team:
- same family-disjoint seed-517 sample with SGD max_iter=100, tol=1e-5;
- independent LinearSVC(C=0.1, max_iter=5000).

Runtime:
- four primary runs: 93.27 s wall, peak RSS 1.75 GB;
- optimizer red-team: 74.40 s wall, peak RSS 1.61 GB;
- Python 3.13.5, pandas 2.2.3, NumPy 2.3.5, scikit-learn 1.8.0, SciPy 1.17.0.

Reproduction:

    python tools/experiments/r030_char_cardinality_prior.py --source1 /path/train_source1.tsv --truth /path/train_ground_truth.tsv --out /tmp/r030.json --train-n 200000 --eval-n 80000 --seeds 517 2026 --red-team

Focused validation:

    python -m unittest tests/test_r030_char_cardinality_prior.py -v

5/5 focused tests PASS; py_compile also PASS.

## Results

The correct same-sample baseline is AUROC 0.5 and AUPRC equal to sample prevalence. For the budget use case, selecting the highest-scored 10% of anchors should capture materially more than 10% of high-cardinality anchors.

| Split | Seed | Prevalence | AUROC | Approx. 95% CI | AUPRC | Top-10% recall | Top-10% lift |
|---|---:|---:|---:|---:|---:|---:|---:|
| entity | 517 | 0.259200 | 0.497573 | [0.493011, 0.502134] | 0.257584 | 0.099633 | 0.9963x |
| entity | 2026 | 0.259750 | 0.498873 | [0.494312, 0.503433] | 0.259793 | 0.100241 | 1.0024x |
| family-disjoint | 517 | 0.263088 | 0.499657 | [0.495114, 0.504199] | 0.262350 | 0.099824 | 0.9982x |
| family-disjoint | 2026 | 0.259825 | 0.499637 | [0.495075, 0.504198] | 0.259885 | 0.101414 | 1.0141x |

Probability quality is also worse than a constant same-sample prior in every logistic run. Family seed 517 has Brier 0.195185 vs constant 0.193872 and log-loss 0.579779 vs 0.576262. Family seed 2026 has Brier 0.193578 vs 0.192316 and log-loss 0.576251 vs 0.572874.

Country slices do not rescue the hypothesis:
- family seed 517: India AUROC 0.503736, US 0.497586;
- family seed 2026: India 0.499844, US 0.498851.

All are operationally chance-level.

### Optimizer red-team

The original 20-iteration SGD emitted a convergence warning, so that failure mode was tested directly on the identical family-disjoint seed-517 sample.

| Model | AUROC | AUPRC | Top-10% lift |
|---|---:|---:|---:|
| SGD, 100 iterations | 0.499584 | 0.262349 | 0.9968x |
| Linear SVM | 0.499503 | 0.261805 | 0.9878x |

The null does not depend on the initial optimizer stopping condition.

### Relation to R009a

R009a's full held-out lightweight-feature model scored AUROC 0.500302, AUPRC 0.258865, and top-10% high-cardinality recall 9.9295%. That is contextual evidence rather than a paired baseline because R030's classifier gate uses deterministic Tier-1 samples. R030 supplies the missing character-text representation check and reaches the same scientific conclusion with orthogonal features.

## Error analysis

1. No useful high-score tail. Across four primary runs, top-10% recall is 9.96–10.14%, essentially the random 10% expectation. Seed-2026 family lift of 1.014x is tiny, unreplicated, and paired with AUROC 0.4996.
2. Repeated brand exposure does not help. The ordinary entity split exposes 34.84% of holdout rows to a normalized name family seen during fit, yet AUROC remains below 0.5 in both replicates.
3. Removing family overlap changes nothing. The strict family split has zero exact normalized-name family overlap and still scores 0.4996 AUROC in both samples.
4. No India-specific signal. India remains around 0.5 despite being the weaker retrieval country.
5. Solver underfitting is not the explanation. A 100-iteration logistic model and an independent linear SVM reproduce the null.

## Interpretation

The evidence supports the mechanism suggested by R009a: target multiplicity appears to be primarily a property of Source-2/Source-3 observation generation and retrieval-side ambiguity, not something reliably encoded in the Source-1 business name. Character n-grams are a much richer lexical representation than R009a's shape/frequency features and still do not rank high-cardinality anchors.

This negative result closes another cheap anchor-only route for adaptive candidate budgets. Candidate-side evidence remains the defensible direction: posting-list fanout, candidate saturation, score distributions/gaps, retrieval provenance, and source balance.

No official macro F0.5, candidate recall, or blocking-oracle delta is claimed because complete S2/S3 inventories cannot be materialized through this chat's raw Drive path. This experiment answers only the prior-feasibility question.

## Risks

- Classifier fitting is Tier-1 sampled, although population/split construction is complete. Two independent samples, country slices, and two optimizer/model red-teams agree.
- A substantially larger nonlinear text model is not mathematically ruled out; the evidence says it is not a high-value next use of the scarce full-target lane.
- Family normalization is Unicode-preserving lowercase plus punctuation/whitespace collapse, not the production accent-folded blocker normalizer. The rejection is specific to this representation.
- Family assignment uses pandas 2.2.3 hash_pandas_object on normalized text; exact fit/holdout family overlap is asserted zero.
- This result does not reject candidate-side adaptive budgets or R009 in general.
- No confirmation/leaderboard reuse: PASS.
- ID/label leakage: PASS.

## Recommendation

REJECT the R030 hypothesis. Do not pursue Source-1 business-name character n-grams as a high-cardinality prior for adaptive retrieval budgets.

The next meaningful R009 gate should use complete target-side retrieval evidence and compare adaptive candidate budgets on identical development/calibration anchors, reporting pair recall, entity recall, all-matches-retrieved rate, blocking-oracle macro F0.5, candidate-count quantiles, country/source slices, and runtime. R019 source-starvation findings should constrain any per-source budget logic.

## Follow-up

No new anchor-only prior task is justified by this result. Recover an existing full-inventory candidate-side adaptive-budget task once the Modal/private-volume lane is available rather than inventing another Source-1 proxy.
