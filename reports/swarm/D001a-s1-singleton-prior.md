# D001a — Source-1-only singleton prior feasibility

## Hypothesis

A true-singleton prior derived only from Source-1 business-name/address structure and corpus-frequency features may identify a high-precision subset of singleton anchors before pair scoring. If successful, this would provide evidence independent of the current pair matcher and could reduce the measured singleton false-positive problem (10.65% overall, 13.51% India on the recorded confirmation baseline).

## Change

This experiment trained a stand-alone singleton classifier using only Source-1 information.

Features (24 total):
- raw and normalized name/address lengths
- name/address token counts
- digit-character and numeric-token counts
- non-ASCII counts
- punctuation and whitespace counts
- normalization-retention ratios
- normalized-name frequency
- normalized-address frequency
- normalized exact name+address frequency
- log1p versions of the frequency features

Country was **not** used as a predictor. Entity IDs were used only for the repository's deterministic split assignment and never entered the feature vector.

Normalization followed the repository intent: lowercase, accent fold, replace non-letter/digit runs with a single space, trim. The analysis runtime lacked the pinned DuckDB 1.5.5 package, so the experiment used an NFD combining-mark removal implementation rather than executing the DuckDB `strip_accents` macro directly. This is recorded as a reproducibility risk below.

## Protocol

Data:
- complete `train_source1.tsv`: **2,206,821 anchors**
- complete `train_ground_truth.tsv`
- **no sampling**
- no Source-2/Source-3 records
- no external entity/business data

Labels:
- singleton = ground-truth matched set is empty
- total singletons: **123,247 (5.584821%)**
- US: 73,896 / 1,323,633 = **5.582816%**
- India: 49,351 / 883,188 = **5.587825%**

Split:
- exact repository `fold517` SHA-256 protocol from `src/ber/experiment.py`
- fit 60%: 1,323,457
- early 15%: 330,681
- calibration 15%: 331,219
- untouched holdout 10%: 221,464

Model:
- CatBoost numerical classifier
- seed 517
- direct country feature excluded
- primary sanity run used AUC early stopping
- red-team confirmation used a fixed **100 trees, depth 7, learning rate 0.08** so early stopping could not prematurely reject a nonlinear signal
- runtime CatBoost version was 1.2.8; repository pin is 1.2.10

Frequency statistics were computed from the complete Source-1 inventory only, without labels. This matches what can be computed on the full test Source-1 inventory at inference.

Successful full-data preprocessing was executed in bounded short-lived chunks to avoid runtime memory accumulation. Aggregate successful chunk compute time was about 50 seconds; the fixed-100-tree training/evaluation run took 17.1 seconds in this environment.

## Baseline

There is no existing Source-1-only singleton classifier in the selected pipeline, so the correct diagnostic baseline for AUPRC is singleton prevalence.

On the untouched holdout:
- singleton prevalence / random-ranking AUPRC baseline: **0.056393**
- constant-prior Brier baseline: approximately **0.053213**

The selected end-to-end pipeline's singleton false-positive rate (10.65% overall / 13.51% India) is context only. This experiment cannot measure a macro-F0.5 delta or singleton-FPR delta because the current candidate/pair-score artifacts are not available in this runtime.

## Results

### Fixed 100-tree red-team run

| Slice | N | Singleton prevalence | AUROC | AUPRC |
|---|---:|---:|---:|---:|
| Fit | 1,323,457 | 0.055705 | 0.523299 | 0.062152 |
| Early | 330,681 | 0.055700 | 0.497378 | 0.055232 |
| Calibration | 331,219 | 0.056205 | 0.501499 | 0.056440 |
| Holdout | 221,464 | 0.056393 | **0.500142** | **0.056496** |
| Holdout US | 132,884 | 0.056372 | **0.500759** | **0.056539** |
| Holdout India | 88,580 | 0.056424 | **0.499226** | **0.056442** |

Holdout AUPRC is only **+0.000103** above the prevalence baseline and AUROC is effectively 0.5. The fit/holdout gap (0.5233 vs 0.5001 AUROC) shows that the model can memorize tiny fit-set quirks, but they do not transfer.

Top-scored holdout purity from the fixed model:
- top 100: 11.0% singleton
- top 1,000: 5.5%
- top 10,000: 5.39%
- top 50,000: 5.678%

There is no practically useful high-precision gating region.

### Early-stopped sanity run

The AUC-early-stopped model selected 8 trees and also produced chance-level ranking:
- holdout AUROC: 0.504656
- holdout AUPRC: 0.057390
- US AUROC: 0.502720
- India AUROC: 0.506954

No calibration threshold achieved even 80% singleton precision. Because AUC early stopping left poorly calibrated probabilities, the fixed-tree run above is the decisive result.

### Corpus-frequency observations

On normalized Source-1 text:
- **39.28%** of anchors share their normalized business name with at least one other Source-1 anchor
- **5.31%** share their normalized address
- exact normalized name+address pairs were unique in this inventory (pair frequency max = 1)

These collisions did not provide generalizable singleton signal.

## Error analysis

The strongest failure mode is not a narrow country slice; it is the absence of transferable anchor-only signal.

1. **US and India behave the same.** Singleton prevalence is almost identical (5.5828% vs 5.5878%), and both holdout AUROCs are approximately 0.5.
2. **Fit-only structure does not generalize.** Fit AUROC rises to 0.5233 while early/calibration/holdout collapse to chance, consistent with weak memorization rather than a real singleton mechanism.
3. **Frequency does not rescue the prior.** Name collisions are common, but name/address frequency features do not separate true singletons from non-singletons out of sample.
4. **The top-score tail is not safe enough for F0.5.** Even the top 100 holdout anchors have only 11% singleton purity; a hard empty-set gate there would be overwhelmingly wrong.

The early-stopped model's singleton and non-singleton score quantiles were nearly identical, reinforcing the same conclusion.

## Interpretation

For this dataset, whether a Source-1 anchor has zero Source-2/Source-3 matches appears essentially independent of Source-1 name/address shape and Source-1 collision frequency.

That means the D001 singleton problem should **not** be attacked with an anchor-only prior. The useful signal almost certainly needs to come from pair/retrieval evidence: top candidate score, score margin, number of credible candidates, retriever provenance, source-2/source-3 agreement, address/number conflicts, and calibration conditioned on ambiguity.

This negative result saves a potentially large amount of tuning time: adding more elaborate Source-1-only heuristics is unlikely to fix the India singleton false-positive problem.

## Risks / red-team checks

- **ID leakage:** PASS. IDs were used only for deterministic split assignment.
- **Label leakage into frequency features:** PASS. Frequencies used Source-1 text only.
- **Split contamination:** PASS. The repository hash split was reproduced; labels are entity-disjoint by anchor.
- **Sampling mismatch:** PASS. Complete Source-1 + ground truth files were used.
- **Country leakage:** PASS. Country was not a model feature.
- **Early-stopping artifact:** CHECKED. A fixed 100-tree rerun remained exactly at chance.
- **Normalizer parity:** minor risk. The runtime lacked DuckDB 1.5.5, so accent folding was implemented with NFD combining-mark removal. The conclusion is so close to chance, across both raw and normalized structural features, that this is unlikely to hide a material anchor-only signal, but exact pinned-runtime replication is still preferable before reusing these exact feature values.
- **CatBoost version:** runtime 1.2.8 vs repo pin 1.2.10. Again, the null result is large enough that a patch-version change is unlikely to reverse it.

No raw records, IDs, predictions, model binaries, or row-level diagnostics are committed.

## Recommendation

**REJECT** Source-1-only singleton gating/prior as a competition direction.

Do not promote any of these features into the decision layer on this evidence. Future D001 work should wait for reusable candidate/pair-score artifacts (or Modal/full-data execution) and build a gate from **pair evidence and ambiguity**, not anchor-only structure.

## Follow-up

Evidence-backed next step: evaluate a candidate-evidence singleton gate using top-1 probability, top-1/top-2 margin, number of candidates above weak thresholds, S2/S3 agreement, retriever provenance, and address-number conflict. That experiment must report official macro F0.5 and singleton FPR on the same fixed evaluation anchors.
