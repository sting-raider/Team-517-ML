# Confirmed rules and strategy changes from the supplied PDFs

Reviewed 25 September 2026. Both PDFs were read in full, with all pages visually inspected. The problem statement has seven content pages and a blank eighth page; the guidelines have two content pages. References below use their printed document order.

Sources:
- `6ab5628d5a817_amazon_ml_challenge_problem_statement.pdf` (Problem Statement).
- `6ab56657b4f1a_guidelines_and_key_instructions_amazon_ml_challenge_2026.pdf` (Guidelines).

## 1. France is an explicit unseen-country test

Problem Statement, Data Description, pages 1-2: training contains US and India; test additionally contains France, absent from training. Records contain `entity_id`, `business_name`, `business_address`, and `country`. There is no separate source column; source is available in the ID prefix and file identity.

This changes the priority of generalization experiments. The concrete challenge is transfer to an unseen country. It is not evidence that France appears exclusively in the private leaderboard: the PDFs do not reveal the country composition of the public/private split.

Proposed changes:

1. Keep the main identity-disjoint validation split and report scores by country, source, cardinality, and missingness.
2. Add two transfer stress tests: train on US and evaluate on held-out India, then train on India and evaluate on held-out US. Keep evaluation labels out of fitting, threshold selection, and calibration for these tests. These are imperfect proxies for France, not estimates of French accuracy.
3. Test a license-compatible multilingual encoder alongside character/token retrieval and language-independent comparison features. Multilingual pretraining is a hypothesis to evaluate, not a guarantee of better entity matching.
4. Preserve raw Unicode and diacritics; test accent-folded text as an additional view. Keep house numbers, units, distinctive words, and missingness features.
5. Treat `country` as an open string label. Do not drop France, restrict the parser to two values, or build a closed two-country one-hot vocabulary. Unknown countries need working retrieval and calibration defaults.
6. Initially use country agreement as a feature and optional retrieval partition with a fallback. A hard cross-country veto needs evidence about country-label reliability and identity semantics; neither PDF guarantees this.
7. Do not import French business/address databases, geographic lookup tables, or externally sourced training examples. The rules do not expressly settle test-set self-supervision or pseudo-labeling; keep the initial model trained on supplied training data and use test records as inference inputs.

Compute implication: the second 4080's early work should include country-transfer evaluation. The first 4080 can train the primary matcher while the 3060/CPU develops the sparse baseline and scorer. Add multilingual training and retriever experiments according to measured errors.

## 2. Metric is confirmed: macro F0.5

Problem Statement, Evaluation Criteria, page 6:

```text
F0.5 = 1.25 * precision * recall / (0.25 * precision + recall)
```

Compute one score per source-one entity, then average equally across entities. Empty truth and empty prediction score 1; empty truth and any prediction score 0. For a nonempty truth set, an empty prediction scores 0. The count form avoids undefined precision:

```text
F0.5 = 1.25 * TP / (1.25 * TP + FP + 0.25 * FN)
```

The PDF's worked example has two true matches and one extra false match, yielding 5/7 = 0.7142857. This agrees with the previous memo's conditional derivation, which is now confirmed. The text's “2×” description does not change the supplied formula.

The helper `utils/validate_submission.py` explicitly checks formatting and IDs only; it does not compute a score (page 4). Implement local scoring from the published equation. The helper's actual source is still absent from this workspace.

## 3. Model constraints

Problem Statement, Constraints, page 5: final model must have an MIT or Apache 2.0 license and at most 8 billion parameters.

Plan around compatible pretrained checkpoints; do not treat every open-weight checkpoint as eligible. Verify the actual checkpoint license and parameter count, not just the library's license. A compact multilingual encoder is worth evaluating under this constraint. The PDFs do not explain whether an ensemble's parameter ceiling is aggregate or per component; keep the planned system comfortably below 8B in total rather than depending on an interpretation near the limit.

External entity-resolution services, registration lookups, geocoding APIs, and internet-derived data augmentation are prohibited (Academic Integrity and Fair Play, page 7). Training and inference should run locally or on rented compute using the provided data and eligible model artifacts.

## 4. Exact output schemas and candidate boundary

Problem Statement, Output Format, pages 3-4:

```text
matching_results.tsv:
source1_entity_id<TAB>matched_entity_ids

candidate_pairs.tsv:
source1_entity_id<TAB>candidate_entity_ids
```

Despite its name, `candidate_pairs.tsv` is not a two-column edge list with one pair per row. Both files require exactly one row for every test source-one ID, with comma-separated S2/S3 IDs in the second field. Use an empty second field for no matches/candidates, no duplicate IDs, valid test IDs only, and unquoted ID lists.

Candidate contents must be the exact final candidates fed to matching inference, after all blocking/filtering stages. An early retrieval union is not the required file if additional candidate filters follow it. Keep that early union separately for diagnostics if useful. Final predictions must be subsets of the submitted candidate lists.

For a cascade, document which stages constitute candidate filtering and where final matching starts. Log the precise boundary and each stage's recall rather than silently substituting one candidate pool for another.

Official validator command, from the resource directory:

```text
python utils/validate_submission.py --matching output/matching_results.tsv --candidate output/candidate_pairs.tsv --test-dir dataset/test
```

## 5. Final archive and submission discipline

Problem Statement, Final Submission Package, pages 4-5:

```text
<team_name>_submission.zip
  output/
    matching_results.tsv
    candidate_pairs.tsv
  code/business_entity_resolution/
    src/
    README.md
    requirements.txt
  Documentation_template.md
```

The code must regenerate both outputs, with exact end-to-end instructions and pinned dependencies. Fill the provided methodology template; a PDF export is also accepted. Do not invent a replacement template before inspecting the supplied one.

Guidelines, Key Instructions, page 1: September 25, 2026, 00:00 IST through September 27, 2026, 23:59 IST; maximum five submissions per day, over three days. The document does not specify the portal's reset implementation. Save each submitted file, configuration/checkpoint identity, local metrics, portal score/status, and timestamp. Use submissions for meaningful validated changes and preserve room for a corrected final artifact. Do not assume unused daily attempts roll over or that the final selection rule is known.

Guidelines, Simultaneous Logins and Accessibility, page 2: no simultaneous logins from multiple devices per participant. This is framed as portal access, not a stated prohibition on training across teammates' computers. Avoid sharing one participant's live portal session across machines; the multi-laptop training plan need not require that.

## 6. Conflicting or unresolved instructions

| Topic | Problem Statement | Guidelines | Practical response |
|---|---|---|---|
| Documentation length | Page 7 says no page limit for the provided template | Page 1 asks for a 1-2-page approach document | Prepare the full reproducibility/template write-up plus a separate concise summary; follow portal-specific upload requirements and seek clarification if only one document is accepted |
| Ranking/shortlisting | Page 6 says final decision uses the private leaderboard | Page 1 says evaluation and shortlisting use both leaderboards | Preserve both results and submission history; prioritize robust held-out performance without inventing an undisclosed combined formula |
| Shortlisted teams and interviews | No interview cutoff established here | Page 1 announces top 100 for a subsequent document step | This does not establish that 100 teams receive internships/interviews; earlier public top-50 interview information describes a potentially different milestone |

The guidelines provide an organizer Google Form for hackathon queries. No questions have been sent. These administrative ambiguities do not prevent model/data work.

Still needed: train/test TSVs, the official validator source, `Documentation_template.md`, record counts, system RAM/storage, and the portal's final-submission selection behavior. No dataset scores or model performance have been measured.
