# M002R — Red-team candidate provenance feature path

**Issue:** #160  
**Target:** M002 / PR #139, head `11e15b321275b4e8b114cdce8581549f2a891f1c`  
**Branch:** `agent/i/M002R-provenance-redteam` (stacked on M002)  
**Recommendation:** FOLLOW-UP — fix is required before empirical M002 benchmarking

## Question

Does M002 preserve the repository's integrity constraints and legacy feature semantics well enough to justify spending full-data compute on the proposed 47-vs-56 matcher ablation?

## Finding

**The original M002 rank feature violated the project's no-record-ID-as-predictive-evidence rule.**

M002 created the model-facing field with:

```sql
row_number() over (
  partition by anchor
  order by retrieval desc, target.entity_id
) as candidate_rank
```

The established blocker is allowed to use target ID as a deterministic tie-break for bounded candidate membership. M002 then exposed the resulting ordinal to CatBoost. When two candidates have identical retrieval scores, their rank therefore depended on lexical record-ID ordering.

That is indirect ID-derived predictive evidence. The effect may be small, but the rule is categorical and the feature is unnecessary in that form.

## Fix

The stacked branch separates two concepts:

1. **selection_rank**: the historical `row_number(retrieval DESC, entity_id)` used only to enforce the candidate cap and preserve legacy candidate membership;
2. **candidate_rank**: `dense_rank(retrieval DESC)`, which is independent of entity-ID ordering and is the only rank value exposed to the matcher.

The final provenance candidate table does not retain `selection_rank`.

This preserves the established cap tie-break while removing ID dependence from the model input.

## Additional test hardening

The M002 synthetic tests were updated to:

- include two candidates with identical text/retrieval but different entity IDs;
- require tied retrieval scores to receive the same model-facing candidate rank;
- derive expected dense ranks from retrieval scores alone;
- require the first 47 provenance-mode feature values to equal the legacy feature vector exactly;
- require `min_key_freq >= 1` validation in addition to rank/hit-count validation.

## Protocol

### Static source audit

Inspected the M002 changes in:

- `src/ber/blocking.py`
- `src/ber/provenance.py`
- `src/ber/experiment.py`
- `src/ber/predict.py`
- `tests/test_m002_provenance.py`

Audit targets:

- record-ID leakage;
- candidate membership/rank semantics;
- hit-family accounting;
- feature order and shape;
- training/inference field-order parity;
- cache/schema failure modes;
- shortlist interaction;
- default 47-feature behavior.

### Executable checks available in this runtime

The local environment has CatBoost, NumPy, and RapidFuzz but not DuckDB. The repo pins DuckDB 1.5.5; this sandbox has no package-network path, so the three blocker/table tests that instantiate DuckDB could not be executed honestly.

I executed three dependency-light checks against the same M002 logic:

1. provenance vector schema/validation;
2. provenance `prepare_groups` assembly, including **56-column output and exact equality of its first 47 values to legacy assembly**;
3. ID-independent dense-rank reference behavior under tied scores.

Result: **3 / 3 passed**.

I also executed the rank window logic over an in-memory SQL engine with tied scores. Two 10.0 candidates received selection ranks 1/2 but both model-facing rank 1; two 9.0 candidates received selection ranks 3/4 but both model-facing rank 2. This verifies the intended separation independently of target-ID ordering.

### Full authored M002 suite

**Not fully executed in this runtime.** The remaining blocker tests depend on DuckDB 1.5.5. Their source was reviewed and strengthened, but a normal repo environment must still run:

```bash
PYTHONPATH=src python -m unittest tests.test_m002_provenance -v
```

before M002 is promoted.

## Static audit results

### Candidate membership

The default `provenance=False` SQL remains the established blocker-v2 path.

In provenance mode, cap membership still uses the same ordering:

```
retrieval DESC, target.entity_id
```

The new dense rank is computed in addition to that selection rank and does not alter which rows pass the cap.

**Expected result:** legacy/provenance candidate membership should remain identical at fixed cap.  
**Execution status:** authored DuckDB parity test still requires a normal repo environment.

### Hit-family accounting

M002 aggregates seven mutually exclusive key-kind buckets:

- exact name `n:`
- exact address `a:`
- name token `w:`
- address token `u:`
- address bigram `v:`
- name/number `h:` and `z:`
- address number/token `d:`

Those buckets cover every blocker-v2 key prefix and are intended to partition `key_hits`. No label information enters the aggregation.

**Static result:** no second leakage mechanism found.

### Training/inference feature ordering

Training materialization selects the original seven `features(...)` arguments, then appends nine provenance values in the order defined by `PROVENANCE_FEATURE_NAMES`.

Inference uses the same split:

- `r[2:9]` for the 47 legacy features;
- `r[9:]` for the nine provenance values.

The strengthened synthetic assembly check confirms a 56-column provenance vector whose first 47 columns exactly equal legacy assembly.

**Result:** PASS for dependency-light assembly test.

### Default behavior

M002 is opt-in through candidate generation, experiment materialization, model config, and inference. The default selected path remains 47 features.

**Result:** no default-path behavior change found in this audit.

## Competition metric

**Not measured.**

No challenge S2/S3 artifact, confirmation/frozen holdout, leaderboard signal, or external identity data was used. The selected confirmation macro F0.5 of **0.928835** is baseline context only.

This red-team run invalidates the original model-facing rank semantics but does not say whether corrected provenance features improve F0.5.

## Risks still open

- **DuckDB execution gate:** candidate-set/retrieval/hit parity has not yet run in this sandbox.
- **Empirical value unknown:** nine extra features may be redundant with retrieval score and text similarities.
- **Rank/cap coupling:** dense retrieval rank is still candidate-generator context and must use compatible training/inference caps.
- **Shortlisting:** the feature records raw retrieval rank before lexical shortlisting; that is coherent but must be held fixed in the ablation.
- **Cache validation:** M002 checks feature-name metadata, but full experiment provenance still depends on correct candidate-table provenance mode.
- **Tiny gains:** any sub-0.001 calibration improvement should be treated as fragile and paired-diff/bootstrap checked before holdout consumption.

## Recommendation

**FOLLOW-UP.**

Before running the expensive M002 full-data ablation:

1. incorporate the ID-independent dense-rank fix;
2. run the complete M002 unit suite in the normal repo environment with DuckDB 1.5.5;
3. assert exact candidate membership, retrieval score, and hit-count parity between legacy and provenance modes at the same cap;
4. only then train the 47-vs-56 depth-10 models on identical candidate IDs;
5. report macro F0.5, singleton FP, US/India, recall/oracle parity, threshold, feature importance, runtime, and paired anchor changes.

The original M002 implementation should **not** be empirically promoted with ID-tie-broken `candidate_rank`.
