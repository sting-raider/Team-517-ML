# Amazon ML Challenge 2026: research and competition strategy

Research date: 25 September 2026. This is an experiment plan, not a claim of achieved competition performance.

The recommended system is a union of complementary candidate retrievers, a feature-based matcher plus a supervised text cross-encoder if permitted, and a decision layer optimized for the official per-business score. The most important investments are realistic validation, difficult negatives, singleton handling, and measuring where the pipeline loses matches.

Update after reviewing the two supplied PDFs: training countries are US and India; test additionally includes France. The metric is confirmed as per-entity macro F0.5 with the specified singleton convention. Final models must have MIT/Apache 2.0 licensing and at most 8B parameters. Exact output schemas and package layout are now known. See [confirmed rules and strategy changes](RULES_INSIGHTS.md), including conflicts between the PDFs. Data files, validator source, and documentation template remain unavailable; data size, singleton frequency, achievable score, and runtime remain unmeasured. No models have been trained or submissions made.

**Evidence boundary.** The supplied PDFs now establish the task, country shift, model restrictions, and ban on external identity lookup/data augmentation. The [organizer's competition listing](https://api.unstop.com/hackathons/amazon-ml-challenge-2026-amazon-1743604) supplies additional event context. France is explicitly in the test set, but neither PDF establishes its proportion in public versus private scoring. Research papers inform methods; their matching datasets and business information must not enter the pipeline. Check the exact license of any pretrained checkpoint; third-party address data and test-set adaptation are not automatically authorized.

## 1. What a difficult private test would actually expose

Complexity should be converted into testable failure modes:

| Failure mode | Why an ordinary system fails | Proposed response |
|---|---|---|
| Same brand, different branch or legal entity | Name similarity overwhelms address disagreement | Explicit number/unit/locality features; mine these negatives; learn the challenge's identity granularity |
| Different businesses at one building | Shared address is treated as identity | Name specificity, address frequency, unit information, competing anchors |
| Acronym, abbreviation, transliteration, spelling noise | Exact tokens and generic embeddings miss matches | Raw and normalized views, character retrieval, training-derived aliases, optional learned retrieval |
| Address contains landmarks or reordered components | Whole-string distance is misleading | Token alignment, component-aware comparisons, learned source-specific corruption patterns |
| Sparse or generic records | Almost any nearby record looks plausible | Missingness indicators, evidence-strength features, explicit empty-set decision |
| Many duplicates for one source-one business | Fixed top-k retrieval silently caps recall | Bidirectional retrieval, saturation diagnostics, selective expansion |
| Unseen businesses or regional conventions | Random pair validation rewards memorization | Entity-disjoint validation plus geographic/name-family stress splits |
| Different singleton prevalence | A fixed threshold becomes poorly calibrated | Row-level calibration; prevalence sensitivity analysis |
| Incorrect transitive links | One bad edge joins otherwise unrelated businesses | Anchored decisions; graph consistency as evidence, not automatic closure |

Some pairs are inherently ambiguous from names and addresses alone. If two unrelated businesses have indistinguishable permitted inputs, model size cannot manufacture reliable identifying evidence. Calibrated abstention is a legitimate part of the solution.

The risk of flattering evaluation is documented by [Wang et al., IJCAI 2022](https://arxiv.org/abs/2205.05889v1), who examine unrealistic benchmark assumptions, and by the [WDC Products benchmark](https://webdatacommons.org/largescaleproductcorpus/wdc-products/), which explicitly varies unseen entities and difficult examples. Their settings are not this competition, but they motivate validation that reproduces retrieval and distribution shift.

## 2. Verify the objective before optimizing it

The transcript's “macro S0.5” ambiguity is resolved: page 6 of the supplied Problem Statement explicitly specifies F0.5, calculated per source-one entity and then averaged, with correct empty singleton predictions scoring one.

**Confirmed metric:** for truth set T and prediction set P:

```text
TP = |T ∩ P|, FP = |P \ T|, FN = |T \ P|
row_score = 1.25 TP / (1.25 TP + FP + 0.25 FN)
          = 1.25 |T ∩ P| / (0.25 |T| + |P|)
row_score(empty truth, empty prediction) = 1
row_score(empty truth, nonempty prediction) = 0
macro_score = mean(row_score over every source-one ID)
```

The standard formula is documented in [scikit-learn's F-beta definition](https://scikit-learn.org/1.5/modules/generated/sklearn.metrics.fbeta_score.html). FP has four times FN's coefficient in this denominator. This is **not** a universal 4:1 decision cost or a fixed optimal probability threshold. Nor does the video's “twice” wording justify multiplying a training loss by two.

Illustrative calculations under the confirmed definition:

| True set size | Correct predictions | Wrong predictions | Row score |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 1.0000 |
| 0 | 0 | 1 | 0.0000 |
| 1 | 1 | 0 | 1.0000 |
| 1 | 1 | 1 | 0.5556 |
| 2 | 1 | 0 | 0.8333 |
| 2 | 2 | 1 | 0.7143 |

Every source-one row has equal final weight. A business with 50 matches does not get 50 times the importance of a singleton. Under the transcript's empty-set convention, predicting empty for every row scores exactly the singleton fraction: record this as a diagnostic baseline.

Evaluate the local scorer on tiny hand-checked cases and the official PDF's worked example (two correct predictions and one false prediction score 5/7). Page 4 explicitly says the supplied validator does not compute scores. Inspect its actual source when available, but implement scoring separately from the published formula. Do not substitute a pair-level macro classification score for the per-entity set score.

### Measure the actual blocking ceiling

For a non-singleton with m true matches and c retrieved true matches, an oracle matcher selecting exactly those c records scores:

```text
oracle_row_score = 1.25 c / (0.25 m + c)
```

For a true singleton the oracle selects nothing and scores one. Average these values over all source-one rows to obtain the validation score ceiling imposed by the current blocker. This is more relevant than global pair recall alone.

## 3. Build validation before the sophisticated model

Split source-one entities before constructing training pairs. Keep all known records of one entity in the same fold. Use positive-label connected components if a right-side record appears under more than one anchor, and investigate that occurrence rather than assuming labels or IDs are wrong.

Maintain one primary held-out split, optionally several entity folds for uncertainty and stacking, and targeted stress splits. Use a fixed final local holdout sparingly so repeated experimentation does not turn it into training data.

| Validation view | Construction | What it checks |
|---|---|---|
| Entity-disjoint primary split | Hold out whole identity groups; stratify coarse cardinality/source/language categories when feasible | Generalization to new businesses |
| Name-family split | Group near-identical anchor names for a separate holdout | Brand/name memorization |
| Geographic split | Hold out locality or postcode groups inferred from provided fields | Regional formatting dependence |
| Country transfer | Train on US, evaluate on India; then reverse; hold out evaluation labels from all fitting and tuning | Dependence on country-specific signals; an imperfect proxy for unseen France |
| Ambiguity slices | Shared addresses, common names, short records, conflicting numbers | False merges |
| Cardinality slices | Zero, one, a few, and many true matches | Singleton and high-multiplicity behavior |
| Controlled corruption | Apply justified, label-preserving transformations to a held-out diagnostic copy | Dependence on punctuation, order, or one field |

The normal validation pass must run the actual blocker over a realistic eligible record pool. Include realistic distractors and inventory size. Never insert the known correct match into validation candidates. A matcher-only experiment may deliberately include all true pairs, but label it as a diagnostic upper bound, separate from end-to-end performance.

Learn aliases, corpus weights, normalizers, augmentation frequencies, retriever weights, and any label-derived graph features using only the training fold. Records can appear as unlabeled search inventory when the evaluation protocol requires it; that is different from using their labels to fit models. Keep a strictly inductive baseline before considering any permitted transductive adaptation.

Report the official macro score alongside candidate recall, per-entity recall, all-matches-retrieved rate, singleton false-positive rate, candidate count percentiles, and runtime. Use paired bootstrap resampling over entities or identity components to compare final score changes. A tiny gain with inconsistent fold results is weak evidence.

## 4. Audit the data and preserve information

Load all files with an explicit tab separator. Keep IDs as strings, preserve leading zeros, disable accidental conversion of literal text to missing values, and namespace IDs internally by source if uniqueness is only source-local. Follow the official output convention when converting back.

First collect record counts, ID uniqueness, null rates, string lengths, scripts/languages, inferred regions, source-specific patterns, exact duplicate groups, match cardinality, unmatched-record prevalence, and positive-pair similarity distributions. Check whether labels are exhaustive for every provided source-one anchor and eligible right-side record.

Maintain multiple representations rather than overwriting the raw inputs:

1. Raw name and address.
2. Conservative Unicode/case/whitespace normalization.
3. Punctuation/token normalization.
4. Name variants retaining and separately downweighting common legal suffixes.
5. Character n-grams and token sets.
6. Address components extracted with uncertainty and missingness flags.

Numbers, unit identifiers, directional words, and distinctive name tokens often separate lookalikes. Preserve them. Normalization that turns several different businesses into the same string should be a feature or retrieval view, not an irreversible truth assignment.

The supplied `country` field covers US and India in training and additionally France in test. Accept arbitrary country strings and retain all test anchors; do not close the pipeline's vocabulary to the two training countries. Preserve Unicode/diacritics in the raw view and test accent folding separately. Use training-pair alignments to propose abbreviations and aliases; require repeated support across businesses so one accidental pair does not become a global replacement rule. External maps, postal databases, registries, and address lookup services are prohibited.

## 5. Retrieval: combine channels and measure their unique contribution

Build candidates separately against sources two and three, then union and deduplicate source-aware pairs. Proposed channels, ordered from cheap to more expensive:

| Channel | Starting design | Main contribution and risk |
|---|---|---|
| Exact/composite keys | Normalized name/address variants; rare name token plus locality token | Cheap high-signal candidates; generic keys can explode |
| Name character retrieval | Sparse TF-IDF character n-grams, initially a small 3–5 range | Typos and spacing; can confuse nearby names |
| Address character retrieval | Separate address index | Recovers corrupted names; shared buildings create negatives |
| Token retrieval | BM25 or weighted token overlap, field-aware | Useful rare-token matches; aliases may share few tokens |
| Learned dual encoder, if eligible | Supervised contrastive learning on supplied identity groups | Learns nonliteral correspondence; training/inference cost and generalization risk |
| Controlled rescue | Training-derived alias/acronym views and selective expansion | Recovers identifiable failure families; easy to overfit |

Use a **union**, not an intersection, of useful channels. An address corruption should not make every name-based candidate disappear. Start with k sweeps such as 10, 25, 50, 100, and 200 where scale allows; these are exploratory settings, not optimal values. Keep each channel's rank, similarity, and presence indicator as matcher features.

Add reverse retrieval: each source-two/source-three record searches source one, and its pairs are added to the forward union. With one-to-many matches, a forward top-k cap can miss a large match set even when each fragment has an obvious anchor. Reverse retrieval can recover these without forcing any record to match.

For each channel report the extra true pairs, extra entities helped, increase in oracle macro ceiling, number of extra candidates, and time. Prefer channels that repair different misses. “More candidates” is useful only if the matcher can handle their harder negative distribution.

As an initial engineering target, explore whether overall validation pair recall can approach 99.5% within budget, while checking the worst important slices. That figure is a target, not a prediction or requirement. [SC-Block](https://arxiv.org/abs/2303.03132v2) evaluates learned blocking at 99.5% validation completeness and shows why candidate size affects total pipeline cost. Its product benchmarks do not establish the attainable recall here.

Measure approximate-neighbor recall against exact similarity search on a manageable sample. A model may rank the correct match well while the approximate index fails to retrieve it. For sparse retrieval avoid materializing the full Cartesian similarity matrix. For dense retrieval budget both vector storage and index overhead.

## 6. Train on the mistakes the system will actually face

Use all available positive links from the training fold and mine negatives from the current retrieval union. The valuable negatives are usually businesses with almost the same name, businesses at the same address, number/unit conflicts, acronym collisions, and candidates that receive high model scores despite being nonmatches.

Mix these difficult examples with some easy negatives and with candidates for true singleton anchors. Do not train only on random pairs or a balanced toy subset and expect the probability outputs to remain valid on production candidates. Calibrate later on the real blocked distribution.

When training labels are complete, an unlisted source-one-to-eligible-fragment pair is a negative. But an unlinked pair of source-two/source-three records is not automatically a negative: both may refer to the same business absent from source one.

For contrastive learning, assign all known records linked to the same anchor the same identity label, use multiple positives, and mask same-identity examples out of the negative set. Unknown fragment-fragment relations should not be assumed distinct. SC-Block's source-aware sampling argument assumes deduplicated input sources; sources two and three here can contain duplicates, so that assumption does not transfer unchanged. See the [method's training-data discussion](https://arxiv.org/html/2303.03132v2).

Keep hard-negative mining inside training folds. If the blocker changes materially, refresh the negatives and revalidate calibration. Sample or weight anchors so high-cardinality identities do not completely dominate training; select weighting by the official macro metric rather than assuming inverse frequency must help.

## 7. Matching: two complementary models before a large ensemble

### Feature model

Train a CatBoost or LightGBM classifier as the first serious matcher. This is a proposed baseline, not a claim that either library is guaranteed to win.

Candidate features should capture:

- Name character similarity, edit distance, token overlap/containment, token order, initials/acronyms, and length ratios.
- Raw versus normalized agreement, unmatched distinctive tokens, and legal-form differences.
- Address character and token agreement, number/unit/postcode/locality matches and conflicts, plus uncertainty in component extraction.
- Missingness and the amount of affirmative evidence available.
- Frequency of the full name, shared address, rare matching tokens, and frequency-conditioned ambiguity.
- Retriever scores, ranks, channel agreement, source identity, and competition among possible anchors for the same fragment.

Shared rare evidence is more informative than shared generic evidence. [Splink's term-frequency treatment](https://moj-analytical-services.github.io/splink/topic_guides/comparisons/term-frequency.html) gives a probabilistic basis for this distinction and also warns about over-weighting rare noisy values. Use corpus-derived features with smoothing rather than making a rare token an automatic match.

Treat address conflicts as learnable evidence first. A hard postcode or number veto may eliminate genuine matches if the challenge contains bad addresses. Add such vetoes only after held-out evidence shows that their precision benefit outweighs the recall loss.

### Text cross-encoder using an eligible checkpoint

A cross-encoder reads both records jointly and predicts whether their fields describe the same business. Fine-tune on supplied labels and mined negatives using a verified MIT/Apache 2.0 checkpoint within the 8B limit. A compact encoder is a sensible first experiment; the explicit France shift now makes a multilingual encoder a priority comparison. Select using both ordinary entity holdout and country-transfer stress tests.

Example serialization:

```text
Record A: name = ... ; address = ...
Record B: name = ... ; address = ...
```

Compare a plain field-labelled representation with compact raw-plus-normalized fields. Measure token-length coverage to avoid truncating addresses silently. Use a classification objective; generating explanations for every pair adds substantial inference work without being necessary for the submission.

[Ditto](https://arxiv.org/abs/2004.00584v3) establishes the supervised sequence-pair approach. Its reported results span several benchmarks and a separate company task, not this challenge. The paper also notes that aggressive augmentation can change the evidence enough to invalidate the assumed label. Test punctuation/format changes and source-observed abbreviations; do not arbitrarily change a house number or remove the sole identifying field while insisting the original label remains certain.

Keep the feature model and cross-encoder if their errors complement each other. Compare simple probability blends against a small stacker trained on out-of-fold predictions. Fit calibration and stacking without labels from the final evaluation fold; nested splitting or a separate calibration fold avoids optimistic evaluation of the decision layer.

## 8. Make predictions as sets, including the empty set

Start with a single validation-tuned threshold. Then test modest source-specific thresholds or a row-aware decision model. Every extra degree of freedom must earn its place on held-out entities.

Train an optional singleton model to estimate q_i = P(no true matches anywhere in sources two/three | available evidence). Its features can include top matcher scores, their count/distribution, name/address specificity, missingness, channel agreement, and competitor-anchor margins. Build its training examples with out-of-fold retrieval and matching, so it sees realistic failures.

Distinguish “no true matches exist” from “the blocker retrieved no true matches.” Otherwise the singleton model may hide retrieval failures. Test empty-set and nonempty-set decisions jointly against the final score rather than choosing a singleton threshold in isolation.

An advanced experimental decoder can compare expected row scores for the empty set and candidate subsets. Under the confirmed F0.5 definition:

```text
U(empty) = P(|T| = 0)
U(P), |P| > 0 = E[1.25 |P ∩ T| / (0.25 |T| + |P|) | observed records]
```

This requires a model of match-count uncertainty and label dependence, including possible missed matches outside the candidate set. The ratio of expected numerator and denominator is not generally the expectation of the ratio. Independent Bernoulli simulation is an approximation; correlated duplicate records can make it overconfident. Searching probability-ranked prefixes is a practical heuristic, not a general proof of optimality. Start simple and retain this only for a repeatable validation improvement. [Waegeman et al., JMLR 2014](https://jmlr.org/papers/v15/waegeman14a.html) gives the relevant decision-theoretic foundation for F-measure maximization.

**Do not force one match per anchor.** Several fragments can all be correct. The gap between the first and second fragment for one anchor does not have the ordinary multiclass interpretation. A potentially useful ambiguity feature is instead the score gap between two different source-one anchors competing for one fragment, if label semantics confirm exclusive ownership.

## 9. Use the three-source structure carefully

Known training links can generate multiple views of an identity, including positive fragment-fragment examples when both fragments share a verified anchor. At inference, agreement between sources can provide supporting features or retrieval expansion.

But predictions are fallible. Do not union-find all thresholded links and emit every implied match. Never merge two distinct source-one anchors merely because both touch a noisy fragment. A Hungarian one-to-one assignment over anchor-fragment pairs would also impose the wrong cardinality.

If labels confirm each fragment belongs to at most one anchor, an optional conflict resolver can choose one anchor or abstain while allowing unlimited fragments per anchor. Re-evaluate the complete macro score after resolution: a constraint can redistribute errors between rows rather than simply remove them.

[TransClean](https://arxiv.org/html/2506.04006v1) studies transitive inconsistencies as a way to identify false positive links in multi-source matching. Borrow its diagnostic idea; its interactive/labeling workflow is not automatically an eligible competition component. The July 2026 [self-serve ER preprint](https://arxiv.org/html/2607.26298v1) also reports substantial risk from false-link propagation. Its teacher-based pipeline and pair-F1 experiments are not evidence of an allowed or superior full solution here.

## 10. Research shortlist and what to transfer

This table separates established method families from newer options. Reading depth varies: core methods above were checked against accessible full-text sections; some secondary papers were screened through authoritative abstracts or project documentation. No published benchmark scores were independently reproduced in this session.

| Reading | Verified contribution | Competition use and limitation |
|---|---|---|
| [Ditto, 2020 preprint / VLDB](https://arxiv.org/abs/2004.00584v3) | Supervised language-model pair classification with augmentation and field handling | Main cross-encoder reference; external domain enrichment is not permitted here |
| [Sudowoodo, 2022 preprint / ICDE 2023 code](https://arxiv.org/abs/2207.04122v2) | Contrastive self-supervision for integration tasks | Optional adaptation on permitted provided records; compare against supervised training when labels are plentiful |
| [SC-Block, 2023 preprint](https://arxiv.org/abs/2303.03132v2) | Supervised contrastive retrieval and candidate-size evaluation | Strong learned-blocker reference; adapt duplicate-source assumptions |
| [Blocking reproducibility study, NAACL 2024](https://aclanthology.org/2024.naacl-long.483/) | Compares blocking and neural IR methods under in/out-of-distribution evaluation | Evaluate an embedding model on actual identity retrieval before committing to it |
| [WDC Products benchmark](https://webdatacommons.org/largescaleproductcorpus/wdc-products/) | Controlled dimensions of difficult cases, unseen entities, and training size | Validation design inspiration; do not import benchmark records |
| [Reality versus ideality, IJCAI 2022](https://arxiv.org/abs/2205.05889v1) | Examines unrealistic entity-matching evaluation assumptions | Avoid reporting success only on curated balanced pairs |
| [Cross-dataset study, EDBT 2025](https://www.bifold.berlin/impact-transfer/publications/view/publication-detail/a-deep-dive-into-cross-dataset-entity-matching-with-large-and-small-language-models) | Evaluates eight matchers on eleven datasets; reports competitive smaller tuned models | Supports measuring training-data design and model cost; transfer-training on those external datasets is outside this task |
| [Match, Compare, or Select?, COLING 2025](https://aclanthology.org/2025.coling-main.8/) | Examines candidate interactions beyond isolated pair decisions | Inspiration for contextual scoring; adapt to zero-or-many outputs and prohibit hosted inference |
| [Serialization study, Findings NAACL 2025](https://aclanthology.org/2025.findings-naacl.437/) | Studies how structured records are presented to language models | Low-cost field-format ablation; knowledge-graph gains do not directly transfer |
| [TransClean, 2025 preprint](https://arxiv.org/html/2506.04006v1) | Uses transitive consistency to locate suspicious predictions | Useful error analysis; no automatic closure or external labeler |
| [UniBlocker, 2024 preprint](https://arxiv.org/abs/2404.14831) | Domain-independent dense blocking pretraining | Method reference; its external corpus/pretraining recipe is not automatically eligible |
| [UCL-Blocker, Applied Soft Computing 2026](https://www.sciencedirect.com/science/article/pii/S1568494626002826) | Unsupervised multi-granularity contrastive blocking with hard-negative emphasis | Lower-priority experiment after the supervised baseline; authors' benchmark gains are not Amazon results |
| [Entity Resolution in Practice, July 2026 preprint](https://arxiv.org/html/2607.26298v1) | Compares matcher families and examines retrieval/false-link failures | Recent supporting evidence; peer-review status unverified and teacher/API setup unsuitable here |
| [F-measure optimal decisions, JMLR 2014](https://jmlr.org/papers/v15/waegeman14a.html) | Studies expected-utility optimization for F-measure | Optional set-decoding foundation after the official metric is confirmed |

Reference implementations: [Ditto](https://github.com/megagonlabs/ditto), [Sudowoodo](https://github.com/megagonlabs/sudowoodo), and [UniBlocker](https://github.com/tshu-w/Uniblocker). Inspect licenses, dependencies, bundled datasets, and model provenance before reuse. Do not run repository scripts that automatically download external matching corpora.

Newer does not mean more relevant. A complex LLM or graph pipeline with a mismatched metric, external teachers, or expensive inference can be a worse competition investment than a well-validated supervised system.

## 11. Run experiments in this order

| Priority | Experiment | Retain only if |
|---:|---|---|
| 0 | Verify files, scorer, singleton convention, eligibility, deterministic export | Local and official checks agree |
| 1 | Conservative exact baseline and all-empty diagnostic | Gives a trustworthy reference and valid file |
| 2 | Multi-channel sparse blocking, source-specific pools, reverse retrieval | Macro oracle ceiling rises at manageable candidate cost |
| 3 | Feature matcher with real retrieved negatives and singleton examples | End-to-end macro score improves across relevant slices |
| 4 | Inspect highest-score false positives and blocking misses | Error families identify a concrete next experiment |
| 5 | Supervised learned blocker, if allowed | Recovers unique missed matches beyond sparse channels |
| 6 | Cross-encoder, if allowed | Adds held-out accuracy worth its measured inference cost |
| 7 | Out-of-fold blend, calibration, singleton-aware decisions | Gains survive a separate holdout or nested evaluation |
| 8 | Source-aware augmentation and targeted retrieval expansion | Improves authentic noise slices without new merges |
| 9 | Graph features, conflict resolution, advanced set decoder | Consistent gain after realistic end-to-end evaluation |
| 10 | Freeze and rerun final pipeline, export archive and methodology | Exact candidate provenance, format validation, and reproducibility pass |

For a roughly 72-hour budget: spend the first few hours on data/scoring/validation; establish a runnable baseline during the first day; devote the middle to candidate recall, negatives, and one complementary model; reserve the final portion for held-out comparisons, runtime, deterministic reruns, and packaging. Compress this order if less time remains. Do not spend the entire window searching architectures.

Compute update from the user: RTX 3060 laptop with 6 GB VRAM and i7-12700H; two teammates each have an RTX 4080 laptop with 12 GB VRAM and i9-13900HX; approximately $650 in AWS credits is available. Start with independent local experiments, including country-transfer evaluation, and use AWS for measured memory, throughput, or deadline bottlenecks. See [the compute plan](COMPUTE_PLAN.md). System RAM, disk capacity, sustained throughput, and AWS account eligibility/quotas remain unknown. Verify each model artifact's MIT/Apache 2.0 license and parameter count under the supplied rules.

Benchmark throughput on a representative candidate sample before a full run. For illustration, 100,000 anchors times 40 candidates from each of two sources is 8 million pairs before deduplication. At a measured r pairs/second, model scoring alone takes approximately 8,000,000/r seconds. Include retrieval, tokenization, disk I/O, and export in the real budget.

## 12. Final artifacts and auditability

The supplied PDFs confirm the leaderboard file matching_results.tsv and the closing archive with both output TSVs, code/business_entity_resolution/src/, README.md, pinned requirements.txt, and Documentation_template.md. Matching headers are source1_entity_id and matched_entity_ids; candidate headers are source1_entity_id and candidate_entity_ids. Both files have one row per test anchor with a comma-separated list or empty second field. The Problem Statement says the template has no page limit, while the Guidelines ask for 1-2 pages; prepare a detailed template and a concise summary and follow portal-specific requirements. See RULES_INSIGHTS.md for the unresolved administrative differences.

Generate candidate_pairs.tsv from the exact final pool passed to matching inference, after all candidate-generation/filtering stages. Do not export an earlier retrieval union if candidates are filtered afterward. Predictions must be a subset of the logged final pool. If graph or rescue stages add pairs, document their position and the candidate/matcher boundary. Keep separate intermediate logs for diagnostics; do not reconstruct candidates from accepted predictions afterward.

Ensure exactly the required source-one IDs, legal right-side IDs, no duplicate matches, correct empty lists, literal tab separation, and official header names. Keep deterministic ordering, seeds, dependency versions, data/config/checkpoint hashes, retrieval settings, and enough provenance to explain why a candidate was considered. Reproduce the package without external record lookups and run the supplied validator.

Record each experiment's split version, blocker, candidate ceiling, official macro score, singleton false-positive rate, source/cardinality slices, calibration setup, wall time, and decision. The companion experiment plan lists hypotheses without invented results.

The Guidelines allow five submissions per day and require version history. They prohibit simultaneous portal logins across devices per participant; this does not expressly prohibit teammate-local training. Reserve submission capacity for the final validated file and retain each artifact/configuration/score.

**Next evidence needed:** train/test TSVs, validator source, Documentation_template.md, system RAM/storage, and portal final-selection behavior. The PDFs resolve the metric and schema; claims of a winning score or a best model still require actual data experiments.
