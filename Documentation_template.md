# ML Challenge 2026: Business Entity Resolution

**Team Name:** Team 517

**Team Members:**
**Submission Date:** 2 October 2026

## 1. Executive Summary

We combine lexical/character blocking with learned multilingual nearest-neighbor retrieval, then score the resulting business pairs using CatBoost and a fine-tuned multilingual cross-encoder. An exact-name recovery rule repairs links whose provider address is missing, and a final ownership pass removes confidently conflicting assignments. The candidate file contains at most 32 Source 2/3 records per Source 1 business. On 3,051 labeled US/India development holdout businesses, the system before the ownership pass scored 0.972095 macro F0.5, versus 0.944783 for the previous 160-candidate system. The selected V13 output scored 0.969 on the public leaderboard, as reported by the team; private accuracy remains unknown.

## 2. Methodology

### 2.1 Problem Analysis

The supplied data has inconsistent names and addresses from three independent sources. A Source 1 business can match zero, one, or many Source 2/3 records. False merges cost more than missed links in the specified macro F0.5 score, and correctly identified singletons earn full credit. Training contains labeled US and India businesses; test also contains France, which has no training labels. The full test set has 1,732,544 Source 1 records and 9,969,589 Source 2/3 records. No external business records, geocoding service, identity API, or externally sourced challenge-specific examples are used.

### 2.2 Solution Strategy

**Approach Type:** Hybrid blocking + classifier + constrained ownership decisions.

**Core Innovation:** Learned multilingual retrieval improves recall while retaining only 32 final candidates per Source 1 business.

All inputs are parsed as tab-separated text. DuckDB stores raw names and addresses alongside deterministic normalized search views; original text is retained for neural models. Country-specific retrieval reduces the search space. Record IDs are used for joins, partitioning, and deterministic ties, never as predictors. Model training uses only supplied training labels. The whole Source 2/3 inventory, including records with no training match, is indexed for blocking.

## 3. Candidate Generation (Blocking)

The first channel retrieves records through bounded name/address token and character keys, and ranks their union by reciprocal-rank and specificity evidence. It keeps up to 160 records internally per Source 1 business. The second channel uses a 117,653,760-parameter multilingual E5-small encoder fine-tuned with positive pairs and hard negatives from 102,125 fitting businesses. It indexes every target record in country-specific, four-shard Faiss IVF2048-SQ8 indexes and searches each shard with 64 probes.

For each business, 16 unique highest-scoring neural neighbors are retained first; the strongest lexical/character candidates then fill the final set to a hard cap of 32. This final union is recorded in `candidate_pairs.tsv` before matching. The full test file has 55,384,406 candidate pairs, or 31.97 per Source 1 record on average, rather than a quadratic comparison against the 9,969,589 target records. On the 3,051-business development holdout, true-pair recall increased from 0.945069 at 160 baseline candidates to 0.978484 at 32 final candidates. The corresponding truth-aware blocking oracle scored 0.992823 macro F0.5. These blocking figures use labels for evaluation only; labels never insert candidates.

## 4. Matching Model

The INT003 CatBoost depth-10 model scores retained lexical/character pairs with numerical name/address comparisons, frequency, and retrieval-rank evidence. An Apache-2.0 multilingual MiniLM cross-encoder, fine-tuned on 402,483 labeled positive/hard-negative pairs from fitting businesses, scores all 32 candidates using the original name and address text. The cross-encoder has 117,641,089 parameters and was trained for one epoch. For a lexical/character pair, the final logit is `logit(CatBoost probability) + cross-encoder logit`. For a neural-only pair, it is `cross-encoder logit - 2`. A threshold of 0.95 was selected on 4,389 calibration businesses using the official per-business metric, then fixed for holdout and test inference. Empty match sets are preserved for singletons.

The pretrained revisions, parameter counts, licenses, and modification notices are recorded in `MODEL_LICENSES.md`, `licenses/`, and the included INT005/M017 training reports. Each checkpoint is below the challenge's 8-billion-parameter limit. The exact selected fine-tuned weights are excluded from Git but included in the final ZIP under `code/business_entity_resolution/models/`, with per-file SHA-256 hashes. Training code is also included; inference from these saved weights avoids dependence on private volume artifacts or nondeterministic retraining. No pretrained model receives external business identity data during challenge training or inference.

After pair scoring, a CPU rule restores a candidate only when its normalized name exactly equals the Source 1 business name, its normalized provider address is empty, and that name occurs once among same-country Source 1 records. This rule was selected on calibration anchors and applied to the unchanged 32-candidate file. On holdout it restored 44 true and 3 false links; broad fuzzy-name, nonempty-address, and target-to-target propagation variants were rejected because they created too many false merges. The rule uses no hidden labels or external data.

The final V13 ownership pass considers only a target already predicted for multiple Source 1 entities. For targets with an address, it compares that address against the competing Source 1 addresses using token-sort similarity. It retains the highest-address-similarity owner only when the best score is at least 50 and exceeds the runner-up by at least 5 for India; the corresponding US and France gates are 20 and 2; otherwise the predictions remain unchanged. This removes 84,654 conflicting predicted edges on the full test output. A labeled same-name competitor proxy found 317,823 correct winners among 317,880 eligible US groups at gate20/2; the India gate50/5 and the complete gate sweep are recorded in `reports/m020_owner_label_gate.json`. That structural proxy is not a full end-to-end score; France has no labeled gate evaluation. The ownership pass never adds an ID outside the frozen candidate file.

## 5. Results & Error Analysis

| Development slice | Previous INT003 | Neural32 | Neural32 plus recovery |
|---|---:|---:|---:|
| Calibration, 4,389 businesses | 0.949121 | 0.977238 | 0.977942 |
| Holdout, 3,051 businesses | 0.944783 | 0.970702 | 0.972095 |
| India holdout, 1,212 businesses | 0.917541 | 0.968360 | 0.968947 |
| US holdout, 1,839 businesses | 0.962737 | 0.972246 | 0.974169 |

The holdout blocker oracle of 0.992823 leaves 0.020728 macro points after the recovery rule for better classification and decision rules. A more compact internal lexical budget of 32 scored 0.969242 before recovery, so the selected implementation retains 160 only for internal ranking while writing 32 final candidates. The labeled development folds have been inspected repeatedly; their scores do not establish a private-test result. France has no labels, and address ambiguity is higher there, so geographic transfer remains the principal uncertainty. The full test export contains 1,732,544 Source 1 rows and 55,384,406 candidate pairs; V13 contains 5,683,583 predicted links and passes both the organizer's matching format validator and the full candidate-subset/target-ID validator. The team reported a public score of 0.969 for the exact V13 file; no private score is known.

## 6. Conclusion

The learned retriever recovers more true links while reducing the final candidate set by fivefold. The multilingual pair model improves decisions on that harder pool, and the missing-address and ownership passes repair measured residual errors. The final archive pairs the selected ownership output with the unchanged 32-candidate file used by the neural model. The selected V13 public score is 0.969; private-test performance remains unmeasured.

## Appendix

### A. Code Artefacts

`src/pipeline/modal_dense.py` trains the encoder; `src/pipeline/modal_dense_retrieval.py` and `src/pipeline/modal_dense_test.py` build complete target indexes; `src/pipeline/modal_crossencoder.py` trains the reranker; `src/pipeline/modal_neural_submission.py` scores the test split and emits both TSVs; `src/pipeline/modal_recover_blank.py` applies missing-address recovery; `src/pipeline/modal_final_owner.py` produces the selected V13 matching file from the unchanged candidate file. Core implementation is under `src/ber/`. The repository `requirements.txt` and Modal images pin direct dependencies. The complete preparation, saved-checkpoint staging, training, inference, validation, and download commands are in `code/business_entity_resolution/README.md`. The final stages are:

```bash
modal run src/pipeline/modal_neural_submission.py --threshold 0.95 --dense-prior -2 --parts-per-country 4
modal run src/pipeline/modal_recover_blank.py
modal run src/pipeline/modal_final_owner.py
```

The final ZIP includes the exact submitted V13 TSV, unchanged frozen candidate TSV, all source under `src/`, exact selected weights, pinned dependencies, model license notices, and a checkpoint/output integrity manifest. Raw training/test data is supplied by the organizer and is not redistributed. No credentials are included. We verified output identity, full output validity, and archive/source integrity during packaging; we did not repeat the full paid training/scoring run. Fresh database import order, ANN rebuilding, and hardware-dependent arithmetic can affect regenerated candidate/inference results; exact bytewise regeneration was not established. The archived output files are the unchanged leaderboard artifacts. Member names are intentionally blank pending the team's final entry.

### B. Additional Results

Aggregate protocols and measurements are in the included INT005/M017 training reports, `reports/capped_match_evaluation.json`, `reports/blank_recovery_submission.json`, `reports/m020_owner_label_gate.json`, and `reports/v13_owner_resolution.json`. The development holdout and leaderboard are distinct. The exact French and private-test accuracy is unknown without organizer evaluation.
