# M001c — train/inference-safe IDF-weighted pair features

**Issue:** #273  
**Branch:** `agent/m/M001c-idf-pair-features`  
**Recommendation:** **FOLLOW-UP / EMPIRICAL GATE**

## Hypothesis

M001a and M001b established that corpus-frequency weighting has substantial dynamic range on the supplied records and does not show a large same-country US/India train-to-test profile shift. The remaining engineering question is whether that signal can be represented in the current INT003 matcher with identical training/inference semantics, while preserving the selected 57-feature V3 path by default.

This task implements that bounded path. It does **not** claim an F0.5 gain because the current chat runtime cannot download the complete Source-2/3 training inventory required for an honest same-candidate CatBoost gate.

## Change

Added an opt-in **feature version 5** rather than reusing feature version 4, which is already occupied by M003's open numeric-commonness branch.

The new block appends eight features to INT003's 57-feature schema:

- name IDF-weighted Jaccard;
- name IDF-weighted overlap/containment;
- name IDF-weighted left coverage;
- name IDF-weighted right coverage;
- the same four metrics for address tokens.

Token document frequencies are materialized by **split + country + concrete source + field**. S2 and S3 are therefore not pooled. For a pair token, its weight is the mean of the Source-1-local IDF and the candidate's concrete-source-local IDF:

```text
idf(side, token) = log((N_side_country + 1) / (df_side_country_field(token) + 1)) + 1
pair_weight(token) = 0.5 * (idf(left, token) + idf(right, token))
```

If a token is absent from one side's corpus profile, that side uses the same smoothed formula with df=0. Pair weights are symmetric; coverage features remain directional.

Files changed:

- `src/ber/idf.py`: IDF profile builder, stale-profile guard, pure reference math;
- `src/ber/v5.py`: V3-compatible pair query and 65-feature schema;
- `src/ber/predict.py`: opt-in feature-version-5 inference path;
- `modal_m001c.py`: private full-data prepare/train gate only;
- `tests/test_idf_features.py`: dependency-light deterministic tests.

Current V3 is unchanged unless a saved model explicitly selects feature version 5.

## Protocol

### Live-state and data checks

The task began from latest `main` after INT003 was merged. Shared Google Drive access was verified.

Required target inventory sizes:

- `train_source2.tsv`: **489,301,488 bytes**
- `train_source3.tsv`: **503,705,637 bytes**

A fresh raw fetch of Source 2 failed with HTTP 413 because the connector rejects files larger than **268,435,456 bytes**. Source 3 exceeds the same limit. No sampled target inventory, partial download, Source-1 proxy, or invented score was substituted.

The current execution container also lacks DuckDB, and package installation cannot reach the network. Therefore the SQL materialization path is syntax-checked but not falsely described as executed here.

### Same-candidate empirical gate

The private/Modal handoff deliberately exposes only `prepare` and `train`:

```powershell
modal run -d modal_m001c.py --action prepare
modal run -d modal_m001c.py --action train --depth 10
```

It copies the already-prepared INT003 V3 database, builds complete train/test source-local IDF profiles, materializes the exact V3 fused cap-160 candidates, appends only the eight IDF features, and trains the same depth-10 CatBoost recipe.

Before any M001c result is accepted, the runner scores the **existing INT003 model** on the first 57 columns and fails closed unless it exactly reproduces these committed same-candidate development references:

| Development split | INT003 macro F0.5 | Pair recall | Blocking oracle |
|---|---:|---:|---:|
| Calibration, 4,389 anchors | 0.9491209588 | 0.9443571616 | 0.9804608439 |
| Holdout, 3,051 anchors | 0.9447832215 | 0.9450685453 | 0.9793001849 |

The current INT003 holdout India macro is **0.9175407676** and singleton FPR is **15.46%**. Those are important secondary diagnostics for the eventual M001c gate.

No confirmation window is exposed by `modal_m001c.py`; `ber.v5.materialize(..., confirmation=True)` explicitly raises. This task does not consume a new frozen window.

## Executed validation

The exact committed core math tests were executed in the available Python runtime:

```text
6/6 PASS
runtime: 1.37 s including interpreter/test startup
```

They cover:

- the exact eight-feature schema;
- IDF positivity and monotonicity;
- pair-weight symmetry;
- exact and empty overlap semantics;
- directional coverage identities;
- rare-token mismatch receiving a larger penalty than common-token mismatch;
- SQL identifier validation for generated table names.

A separate deterministic randomized reference check used seed 517 over **10,000** weighted token-set pairs. Jaccard/overlap symmetry, directional coverage swapping, finiteness, and [0,1] bounds all passed within 1e-12 floating-point tolerance (1.58 s including interpreter startup).

`py_compile` passes for `src/ber/idf.py`, `src/ber/v5.py`, and `modal_m001c.py`.

## Result

No official macro F0.5 delta is claimed in this chat.

The completed result is an executable, attribution-clean empirical gate that:

1. preserves INT003 candidates and the first 57 feature columns;
2. uses complete split-local source/country/field profiles when run on the private full-data database;
3. keeps S2 and S3 frequencies separate;
4. keeps left and right countries separate rather than assuming cross-country candidates are impossible;
5. fails closed on missing/stale IDF profile tables;
6. fails closed if the INT003 baseline metrics or candidate ceiling drift;
7. cannot accidentally consume a confirmation window.

This is materially stronger than handing the coordinator only the M001a feasibility helper, because the remaining experiment can now be run as a one-variable matcher ablation.

## Error analysis / red team

### Main unresolved risk: SQL expansion cost

The query explodes deduplicated name/address tokens per candidate pair before aggregation. At roughly 16 million training pairs in INT003, this may be CPU/memory heavy. The private gate must record materialization wall time and memory. A runtime failure is a valid negative result; it should not trigger a silent sampled replacement.

### Feature redundancy

M001 may overlap with existing unweighted token overlap and with M003 numeric-commonness. The first full-data gate must run **M001 alone** on top of INT003 so attribution remains clean. Combining M001/M003/M009 before measuring each alone would turn three hypotheses into one indecipherable soup.

### Test-local corpus statistics

INT003 already computes unlabeled test-local inventory frequency features at inference. M001c follows that existing split-local pattern and uses no test labels. Organizer clarification issue #270 is active; if it changes the permitted interpretation of test-set corpus statistics, M001c must be revisited before production use.

### No DuckDB execution in this chat

The pure feature math and Python syntax were executed, but the DuckDB SQL has not been run in this container because DuckDB is absent and network package installation is unavailable. The private prepare action is therefore a required execution gate, not paperwork.

## Compliance / leakage audit

- supplied challenge records only;
- no external business lookup, registry, Maps, geocoding, company sites, or entity-resolution API;
- no record IDs in predictive features;
- no positive insertion into candidates;
- no France labels or pseudo-labels;
- no leaderboard feedback used as labels or tuning signal;
- no confirmation/frozen-holdout consumption;
- candidate generation remains INT003 fused cap 160;
- IDF tables use text/source/country/field corpus statistics only.

## Recommendation

**FOLLOW-UP / EMPIRICAL GATE.**

Run the private full-data `prepare` then `train` actions. Reject the experiment immediately if INT003 parity does not reproduce exactly. If parity passes, compare M001c against INT003 on the same calibration and 3,051-anchor development holdout and report:

- official macro F0.5;
- India and US macro F0.5;
- singleton false-positive rate overall and by country;
- candidate pair/entity recall and blocking oracle parity;
- selected threshold;
- paired improved/regressed anchors;
- materialization/training runtime and memory.

A tiny positive delta should be replicated before promotion. No new confirmation window should be consumed for an unreplicated development gain.
