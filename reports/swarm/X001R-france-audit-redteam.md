# X001R — Red-team of X001 France census semantics

## Hypothesis

X001's full Source-1 census may contain semantic/reproducibility mismatches even if the scan itself is deterministic. The red-team question is whether the committed aggregates and prose mean exactly what the helper computes.

## Scope and protocol

- Reviewed PR #32 at head `164c2694e3b0006c4e8f5917215cb966add6c053`.
- Compared `src/ber/france_audit.py`, `tests/test_france_audit.py`, the committed JSON aggregate, and the Markdown report.
- Cross-checked production normalization in `src/ber/data.py`, blocker semantics in `src/ber/blocking.py`, and feature construction in `src/ber/features.py`.
- No new challenge rows were read and no French labels were invented.
- This is a static consistency audit; no F0.5 delta is claimed.

## Findings

### 1. The documented reproduction command does not reproduce the committed JSON artifact

The report says to run:

`python -m ber.france_audit --train-source1 ... --test-source1 ... --out reports/swarm/X001-france-source1-audit.json`

But the helper currently writes a schema with:
- `protocol` as a string,
- `train.path`, `train.elapsed_seconds`, `train.countries`,
- `test.path`, `test.elapsed_seconds`, `test.countries`,
- `test.france_details`.

The committed `reports/swarm/X001-france-source1-audit.json` instead has:
- `protocol` as an object,
- direct country maps under `train` and `test`,
- a separate top-level `france` object,
- a curated subset/renaming of metrics.

Therefore the committed machine-readable artifact is not the direct output of the documented command. Either a missing post-processing step must be committed/documented, or the artifact/helper must be made schema-identical.

**Impact:** reproducibility/provenance defect. It does not by itself invalidate the raw census numbers, but another agent cannot regenerate the checked-in artifact from the stated command.

### 2. Raw character length is used as evidence about normalized CatBoost length features

`update_field()` accumulates `len(text)` on the raw Source-1 string. The report correctly states that the model's `left_len/right_len/len_ratio` features are computed after production normalization, but then cites the raw census means (France name 19.42, address 50.07, etc.) as evidence for that feature family's distribution shift.

Production normalization lowercases, applies DuckDB `strip_accents()`, replaces every non-letter/non-digit run with a space, and trims. This can change length, especially in a slice where 82.819% of addresses contain hyphens.

**Impact:** the quoted means are valid raw-format statistics, but they are not measurements of the actual model length features. The report should either relabel them as raw lengths or compute the same production-normalized lengths before drawing a feature-distribution conclusion.

### 3. Token occurrence counts are described as row/document frequencies

For each France row, the helper executes:

`france_name_tokens.update(word_tokens(nfkd_fold(name)))`

and likewise for addresses. `Counter.update(list_of_tokens)` counts token **occurrences**. It does not count rows/documents containing each token.

The report interprets these values as row prevalence, e.g. `sarl in 73,486 rows (28.32%)`, and later says `rue (170,819 rows)`. Those denominators are not established by the code. A row containing a token twice contributes 2.

**Impact:** common-token direction is plausible, but the row percentages/counts are not justified. Either:
- change the scan to update with `set(word_tokens(...))` for document frequency and rerun, or
- relabel existing values as occurrence counts and remove row percentages.

A focused test should include a row with a repeated token so this distinction cannot regress silently.

## Findings that survived the red-team

The following core X001 observations are not affected by the three defects above:

- France has 259,452 Source-1 test anchors in the checked aggregate.
- The non-ASCII and NFKD-change percentages are record-level counters in `update_field()`, so their denominators match the report.
- The production matcher does consume normalized `n/a` strings rather than raw business text for the 44 name/address pair features.
- `retrieval` and `key_hits` are direct model features, and blocker frequency is country-conditioned because keys hash `(country, key)`.
- X001 correctly labels NFKD as a diagnostic proxy rather than an exact implementation of DuckDB `strip_accents()`.
- No French F0.5 or pair-level performance claim is made.

## Risk assessment

The three defects affect provenance and interpretation, not the existence of a France representation shift. They are still worth fixing because downstream agents are likely to reuse the token prevalence and length claims when designing IDF, stopword, or calibration changes.

## Recommendation

**FOLLOW-UP / REQUEST CHANGES on PR #32 before merge.**

Minimum safe correction:
1. make the documented command reproduce the checked JSON exactly (or document/commit the transformation);
2. relabel raw length statistics or compute production-normalized length statistics;
3. fix token document-frequency semantics or relabel occurrence counts and remove row percentages;
4. add focused tests for output schema and repeated-token behavior.

No production scoring change is required for this correction.
