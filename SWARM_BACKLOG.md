# SWARM_BACKLOG.md — initial high-value queue

Coordinator integration INT001 (integration/submission-v2): matched-cap160 training on
the original fit anchors plus fit-fold anchors at hash positions 50,001:200,000;
inventory-frequency/rank features; paired baseline comparison; Modal L4 training.
Public submission v1 scored 0.898. No research branch is a promoted model by itself.

This is a seed queue, not a sacred roadmap. Agents should create more atomic tasks as evidence appears. Claim before working.

Priority legend:
- P0: structural bottleneck / potentially large gain
- P1: likely useful
- P2: exploratory / supporting

## Retrieval / blocking

- **R001 P0** Build a missed-positive taxonomy on development anchors at cap 640. Quantify miss categories by country/source: no shared tokens, name replacement, transliteration, address number mismatch, sparse address, reordered address, etc.
- **R002 P0** Character 3–5 gram inverted retriever for names. Measure marginal positives recovered over blocker v2 and added candidates.
- **R003 P0** Character 3–5 gram inverted retriever for addresses.
- **R004 P0** Mixed name+address char-ngram retrieval with weighted union.
- **R005 P0** BM25/IDF-weighted token retriever over names.
- **R006 P0** BM25/IDF-weighted token retriever over addresses.
- **R007 P0** Rare-token/rare-number high-precision blocks.
- **R008 P0** Reverse retrieval: retrieve S1-like neighbors from S2/S3 and propagate candidate evidence back to anchors without using labels at inference.
- **R009 P0** Adaptive candidate cap based on ambiguity/posting-list fanout instead of uniform 640.
- **R010 P0** Country/source-specific blocker variants, evaluated with identical matcher.
- **R011 P1** Transliteration-tolerant lexical representation learned/validated without external entity data.
- **R012 P1** Phonetic retrieval usefulness by country/language slice.
- **R013 P1** Multi-probe combinations: address number + rare token, postcode-like token + name fragment, locality-like token + name fragment.
- **R014 P1** Measure oracle ceiling at caps >640 or recall-first unbounded union before pruning.
- **R015 P1** Learn cheap candidate-pruning model that preserves recovered positives from a much wider retriever.
- **R016 P1** Analyze whether positive target records are often near one another under source-specific lexical indexes and exploit that safely.
- **R017 P1** Duplicate/near-duplicate cluster retrieval inside S2 and S3 to recover siblings after one strong link.
- **R018 P1** Candidate-source provenance features and union ablation: quantify value of every block independently.

## Data forensics

- **F001 P0** Learn source-specific token deletion/insertion frequencies from positive pairs.
- **F002 P0** Learn source-specific character/edit corruption patterns from positive pairs.
- **F003 P0** Address number/unit corruption analysis by country and source.
- **F004 P0** Hard-negative audit: same address, different business.
- **F005 P0** Hard-negative audit: same/common name, different address.
- **F006 P1** Legal suffix and corporate-form behavior learned from supplied labels only.
- **F007 P1** Token discriminativeness / IDF distributions by source and country.
- **F008 P1** Missing-address positive-match behavior and best fallback evidence.
- **F009 P1** Name-only vs address-only positive modes and their proportions.
- **F010 P1** Country/source text-length, script, punctuation, abbreviation, and normalization drift.
- **F011 P1** Compare test-vs-train unlabeled distributions for US/India; isolate shifts that could hurt calibration.
- **F012 P1** France unlabeled source-format audit: character classes, diacritics, address token shapes, numbers, punctuation, source asymmetries. No invented labels.

## Matcher / features

- **M001 P0** Add corpus-frequency/IDF-weighted token similarity features.
- **M002 P0** Add candidate-rank and retriever-provenance features.
- **M003 P0** Add rare-number agreement/conflict features.
- **M004 P0** Address component soft alignment rather than whole-string-only similarity.
- **M005 P0** Train with substantially larger anchor sample; measure whether current ~18k fitting anchors are the bottleneck.
- **M006 P0** Hard-negative mining from high-scoring false candidates.
- **M007 P1** Source-specific CatBoost models or source interaction features.
- **M008 P1** Country-aware model interactions evaluated with transfer stress.
- **M009 P1** Character n-gram similarity features for name/address pairs.
- **M010 P1** Token-level optimal/greedy soft alignment features.
- **M011 P1** Calibrated multilingual encoder pair similarity using only a rules-compliant checkpoint.
- **M012 P1** Cross-encoder experiment on a bounded difficult-pair set if a compliant checkpoint and runtime permit it.
- **M013 P1** Ensemble CatBoost seeds / feature subsets; quantify error complementarity before averaging anything.
- **M014 P2** Monotonic constraints or explicit conflict penalties for strong address-number disagreement.

## Decision / set-level

- **D001 P0** Build a dedicated singleton classifier/gate and evaluate singleton FPR vs non-singleton recall.
- **D002 P0** Expected-F0.5 selection from calibrated candidate probabilities rather than one global pair threshold.
- **D003 P0** Per-anchor adaptive threshold using top-score, margin, candidate count, and evidence strength.
- **D004 P0** Source-specific thresholds for source 2 vs source 3.
- **D005 P1** Country-specific thresholds for labeled countries plus transfer-risk analysis.
- **D006 P1** Cardinality prediction and use it as a set-size prior.
- **D007 P1** Top1/top2/top3 score-gap features for ambiguity.
- **D008 P1** Joint source2/source3 evidence: use agreement between independent sources as confidence evidence without forcing transitive closure.
- **D009 P1** Calibrate probability separately by retrieval provenance / ambiguity bucket.
- **D010 P1** Analyze false positives by F0.5 cost and identify safest precision-first cuts.

## France / robustness

- **X001 P0** Evaluate every current feature for language/country specificity; identify features likely to fail on French formats.
- **X002 P0** Unicode/diacritic normalization ablation.
- **X003 P1** Train corruption augmentation from US/India positive pairs and test transfer on held-out country.
- **X004 P1** Compare language-agnostic char models vs token heuristics under US↔India transfer as a proxy stress test.
- **X005 P1** Rules-compliant multilingual embedding retrieval on supplied text only.
- **X006 P2** Unsupervised French candidate-density and score-distribution analysis to detect calibration drift without labels.

## Infrastructure / evaluation / red team

- **I001 P0** Fast standard benchmark command that runs one fixed dev slice and emits all required metrics as JSON.
- **I002 P0** Experiment config hashing + stale-cache detection.
- **I003 P0** Central candidate cache format so multiple matcher agents reuse identical candidate sets.
- **I004 P0** Modal batch runner for registered swarm experiments against the private volume.
- **I005 P0** Frozen final-holdout mechanism that makes accidental repeated evaluation difficult.
- **I006 P0** Leakage scanner: IDs/features/splits/caches/positive insertion.
- **I007 P1** Pair-bootstrap/entity-bootstrap comparison utility for tiny deltas.
- **I008 P1** Error-set diff tool: which anchors improved/regressed between two experiment outputs?
- **I009 P1** Runtime/memory profiler per pipeline stage.
- **I010 P1** Integration harness for combining two PRs and rerunning the same benchmark.
- **I011 P1** Red-team current CatBoost baseline for train/validation contamination.
- **I012 P1** Red-team retrieval study for accidental positive injection or candidate leakage.
- **I013 P2** Automatic Markdown report generation from experiment JSON.
- **I014 P2** Leaderboard submission ledger recording config hash, code SHA, local validation score, and public score without using public score as training labels.

## Suggested first wave

If many agents are available immediately, prioritize these in parallel:

R001, R002, R003, R005, R006, R007, R014, F001, F003, F004, F005, M001, M002, M003, M005, M006, D001, D002, D003, I001, I003, I004, I005, I006.

That wave attacks the known ceiling, India weakness, singleton precision, and experiment throughput simultaneously.


## Coordinator integration — September 26

- **INT001 COMPLETE / DO NOT DEPLOY** Larger matched-pool training compared depths
  8 and 10. Calibration improved, but ordinal rank encoded ID tie ordering;
  archived reports remain in `reports/int001_depth*.json`.
- **INT002 CLAIMED / RUNNING** Correct score-only dense rank; rebuild features,
  train depth 10, confirm on predeclared 40k:45k window, export second submission.
  Branch: `integration/submission-v2`. Follow-up code and final measured report
  will be integrated by the coordinator.
- **INT003 FOLLOW-UP** Train/evaluate complementary character retrieval at cap160
  using `reports/int001_retrieval.json` as retrieval-only evidence. Compare both
  base and source-aware rank fusion; source-aware gains overall but loses some
  India recall. No matcher score claimed yet.


## Coordinator integration — v3

- **INT003 CLAIMED** Train and evaluate a cap-160 lexical-plus-name-character
  retriever with score-only reciprocal-rank fusion and the full target inventory.
  Source-1 sample 50,001:200,000 fit fold only; preserve original early,
  calibration, and development holdout folds. Use a new 45,001:50,000
  confirmation window only after calibration/model selection. Compare to the
  confirmed v2 matcher on identical anchors, candidate budget, singleton and
  country slices. Branch `integration/submission-v3`. No external entity data.
