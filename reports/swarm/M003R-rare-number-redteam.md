# M003R — Red-team rare-number commonness semantics

## Recommendation

**FOLLOW-UP after fix.** M003's modeling idea remains plausible, but the reviewed PR contained one material implementation defect that would make the DuckDB numeric extractor use a double-escaped Unicode property pattern. The red-team branch fixes it and adds a regression guard. Do not spend a full CatBoost gate on the unpatched M003 head.

No official macro F0.5 is claimed. The full S2/S3 files remain above this chat connector's raw-transfer ceiling.

## Scope

Stacked on M003 / PR #238. Audited:
- `src/ber/number_commonness.py`
- `src/ber/v4.py`
- `src/ber/predict.py`
- `src/ber/v3.py` and `src/ber/v2.py` for train/inference parity
- `src/ber/features.py` for existing number-token semantics
- `tests/test_number_commonness.py`

No challenge labels, confirmation/frozen holdout, leaderboard tuning, France labels, external identity data, or new candidate/model scores were used.

## Material defect found

M003 defined:

```python
NUMBER_TOKEN_REGEX = r"\\p{Nd}+"
```

That Python raw string contains **two backslash characters** before `p`. The value is interpolated into an ordinary DuckDB SQL string literal:

```sql
regexp_extract_all(s.n, '\\p{Nd}+')
```

DuckDB uses RE2 for regular expressions, and its documentation examples pass regex escapes such as `\d+` with one backslash. DuckDB documents backslash escape processing under explicit `E'...'` escape literals; the M003 query uses an ordinary quoted literal. Therefore the doubled Python backslash is not needed to survive SQL parsing and changes the regular expression seen by the engine.

The consequence is severe: the intended Unicode decimal-digit property is `\p{Nd}+`; the reviewed constant represents a literal-backslash escape form instead. A reference Unicode-regex check on ASCII, Arabic-Indic, and fullwidth digits produced zero matches with the double-escaped pattern and the expected digit runs with the single-escaped pattern.

This defect was partly protected by the original tests because they asserted the same wrong double-escaped constant.

## Fix

Red-team branch changes the constant to:

```python
NUMBER_TOKEN_REGEX = r"\p{Nd}+"
```

and changes the regression checks so generated SQL must contain the single-escaped Unicode-property form and must not contain the doubled form.

Commits:
- `40b44ef`: correct DuckDB Unicode digit regex escaping
- `556dd07`: guard generated SQL against double escaping

## Independent checks

Dependency-light adversarial reference execution in this runtime:

- double-escaped pattern on ASCII `12`: no match
- corrected pattern on ASCII `12`: match
- corrected pattern on Arabic-Indic `٣٤`: match
- corrected pattern on fullwidth `５６`: match
- no-digit input: no match
- rare/shared/unmatched commonness reference semantics: pass
- repeated-token set semantics: pass
- empty evidence semantics: pass

Result: **8/8 reference checks pass after the fix.**

DuckDB itself is unavailable in this container, so this is not represented as an executed DuckDB integration test. The exact repository DuckDB suite should run before selecting V4 for production.

## Train/inference parity audit

After the regex fix, no second static parity blocker was found:

- V4 materialization reuses the exact INT003 fused candidate function.
- Both materialization and inference build split-local number commonness tables before evaluating the same V4 pair query.
- Source-1 DF is country/field-local; target DF is country/source/field-local.
- Target profile joins pin to the actual candidate source, preventing S2/S3 cross-contamination.
- Numeric tokens are deduplicated per record before DF counting.
- V4 preserves V3 as an exact 57-feature prefix and appends eight features.
- Default feature versions 1–3 retain their prior inference branches; V4 is opt-in.
- The V4 model config/schema check fails closed if saved feature names disagree.

One transfer risk remains by design rather than as a code defect: raw log document frequencies are inventory-size-dependent transductive statistics. The eventual full-data gate should therefore report US/India slices and avoid interpreting the values as calibrated probabilities.

## Red-team conclusion

The original M003 PR should **not** go directly to a private full-data training gate without the escape fix, because the intended number profiles may be empty/zero and any measured result would test the wrong feature.

With the fix applied, the primitive is suitable for the already-specified same-candidate empirical gate. Promotion still requires measured official macro F0.5, India/US, singleton FPR, threshold, paired deltas, and candidate-set parity on the private full-data runtime. Tiny gains should be replicated.

## Runtime / limitations

Reference adversarial checks run in well under one second. Full DuckDB execution and CatBoost scoring are blocked in this chat runtime by the missing DuckDB dependency and the Drive connector's 256 MiB per-file raw transfer limit for S2/S3.
