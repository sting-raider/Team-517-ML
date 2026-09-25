# ML Challenge 2026: Business Entity Resolution

**Working draft:** this records the selected first submission configuration and its
independent local result. Add full-export validation and team details before the
final archive. Multilingual alternatives remain experimental.

**Team Name:** Team 517
**Team Members:** To be completed by the team before final submission
**Submission Date:** Initial implementation, 25 September 2026

## 1. Executive Summary

We retrieve up to 640 candidates per entity using complementary name and address
keys, then score 47 numerical comparison features with CatBoost. A separate
5,000-entity confirmation sample scores 0.928835 macro F0.5. French accuracy and
leaderboard performance are not known.

## 2. Methodology

### 2.1 Problem Analysis

The supplied source files contain 24,229,173 records across training and test. Names
vary through spelling changes, web-domain forms, word order, transliteration, legal
suffixes, and occasionally complete replacement. Addresses may be shortened,
reordered, missing, or contain different number formats. Training contains US and
India, while France is present only in test. The training singleton rate is 5.5848%.

### 2.2 Solution Strategy

**Approach Type:** Blocking and supervised classifier.

DuckDB stores the full supplied inventory on disk with a 4 GB query memory limit.
Raw text is preserved. Separate normalized views lowercase text, fold accents, and
replace punctuation with spaces. Country is an open string label; all test countries
are processed. Retrieval uses same-country partitions because all observed labeled
positive links agree on country. Mislabeled-country records remain a limitation.

## 3. Candidate Generation

Blocking uses normalized compact names and addresses; name prefixes paired with
address numbers; name words; address words; adjacent address-word pairs; and address
numbers paired with address words. Posting lists over 1,000 records are omitted, and
the four rarest usable keys per token family are selected. Inverse-frequency evidence
and exact-field bonuses rank the union; its first 640 candidates are scored by the
classifier. Hashes are internal retrieval keys and are not model features.

The 640 cap was selected for its measured macro F0.5 gain over smaller budgets.
Candidates have median count 611 and pair recall 0.947246 on independent
confirmation. We measure lost links explicitly; blocking remains the main ceiling.

The exported `candidate_pairs.tsv` contains exactly the final candidates sent to
CatBoost. The full inference candidate total is recorded in the export validation
report when the complete run finishes.

## 4. Matching Model

The model uses 47 numerical features: name/address string, token-sorted, token-set,
compact-string, and Jaro-Winkler similarities; lengths and missingness; directional
token coverage; number agreement/conflict; retrieval evidence; and record source.
Business IDs and country categories are excluded from model features.

CatBoost uses 1,226 trees, depth 10, learning rate 0.045, L2 regularization 10,
and seed 517. Each anchor's
candidate rows receive equal total training weight. The development sample contains
30,000 reference entities; fitting, early stopping, threshold calibration, and
development holdout are separated by a stable SHA256-based 60/15/15/10 partition.
The complete unlabeled S2/S3 inventory is searched in every partition. The data audit
found no target assigned to multiple anchors. A separate 5,000-anchor sample is used
only for confirmation. Threshold 0.625 maximizes calibration macro F0.5 on the selected
candidate configuration. No pretrained model is used in this first submission;
CatBoost is Apache-2.0 software.

## 5. Results and Error Analysis

Confirmation macro F0.5 is **0.928835** (US **0.948339**, India **0.900722**).
The entity-bootstrap 95% interval is [0.924276, 0.933230]. This does not quantify
unseen-France uncertainty. Singleton false-positive rate is 10.653%; retrieval's
oracle macro ceiling is 0.980951. Country-transfer stress tests show substantial
degradation, particularly from US-only training to India.

Remaining weaknesses include missing candidate links, ambiguous similar names at
shared addresses, severe name replacement/transliteration, and singleton false
merges. See `reports/RESULTS.md` and the machine-readable experiment reports for exact
protocols and comparative measurements. No public/private leaderboard claim is made.

## 6. Conclusion

Address retrieval substantially improved the initial baseline. Further effort
should target complementary retrieval, multilingual generalization, and false merges,
using development data while preserving a fresh confirmation set.

## Appendix

### A. Code Artefacts

All implementation is under `src/ber/`. The README provides exact preparation,
retrieval, fitting, calibration, confirmation, inference, and validation commands.
Direct dependency versions are pinned. Inference uses bounded batches, multiple CPU
workers, checksummed resume points, and one output row per test reference entity.
The package is intended to run using only the supplied challenge files. No external
business databases, APIs, geocoding, or externally generated training data are used.

### B. Additional Results

Aggregate audits, threshold curves, country-transfer experiments, and confirmation
statistics are versioned under `reports/`. Row-level diagnostics, checkpoints, original
datasets, PDFs, and generated predictions are kept local and excluded from Git.
