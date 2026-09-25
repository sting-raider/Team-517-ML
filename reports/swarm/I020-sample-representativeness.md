# I020 — Development / confirmation sample representativeness audit

**Issue:** #153  
**Branch:** `agent/i/I020-sample-representativeness`  
**Recommendation:** **PROMOTE** the sampling protocol with a holdout-composition warning; do not use the 3,051-anchor holdout alone to adjudicate tiny India/singleton deltas.

## Hypothesis

The deterministic 30,000-anchor development block and the two already-consumed 5,000-anchor confirmation windows should resemble the complete training Source-1 population on country mix, truth cardinality/singletons, and observable Source-1 text sparsity. Material skew would make small measured deltas less trustworthy even if the metric implementation itself is correct.

## Change

Added `src/ber/sample_audit.py`, a deterministic aggregate audit that reproduces:

- anchor ordering: `md5('sample517:' || entity_id)`;
- development positions `[0, 30000)`;
- already-consumed confirmation windows `[30000, 35000)` and `[35000, 40000)`;
- development folds from `sha256('fold517:' || entity_id)` using the repository's 60/15/15/10 split.

The tool reads complete Source-1 + ground truth only. It does not touch S2/S3, candidate sets, model scores, a new confirmation window, or leaderboard feedback.

## Protocol

Complete supplied files:

- `train_source1.tsv`: 2,206,821 anchors, 210,069,713 bytes.
- `train_ground_truth.tsv`: 2,206,821 truth rows, 127,015,583 bytes.

The empirical pass was executed in the chat analysis runtime with vectorized full-file processing. For exact hash-window reconstruction, the first 64 bits of every anchor's MD5 sample key were checked and were unique across all 2,206,821 anchors; therefore sorting by that prefix is identical to sorting by the complete MD5 key for this population.

No sampling was used for the population aggregates. The descriptive `z_hash_random` values below use the full-population proportion as the reference under pseudo-random hash sampling. They are diagnostics, not multiple-testing-adjusted hypothesis tests.

Repository reproduction command:

```bash
python -m ber.sample_audit \
  --source1 /path/to/train_source1.tsv \
  --truth /path/to/train_ground_truth.tsv \
  --db artifacts/i018.duckdb \
  --out reports/swarm/I020-sample-representativeness.json
```

Focused helper tests are in `tests/test_sample_audit.py`.

## Integrity / parity checks

- Source-1 anchors: **2,206,821**.
- Ground-truth rows: **2,206,821**.
- Development fold counts: fit **17,990**, early **4,570**, calibrate **4,389**, holdout **3,051**.
- Development ↔ confirmation-1 overlap: **0**.
- Development ↔ confirmation-2 overlap: **0**.
- Confirmation-1 ↔ confirmation-2 overlap: **0**.
- Confirmation-1 composition exactly matches the committed historical report: **2,006 India / 2,994 US / 274 singletons**.
- Confirmation-2 composition exactly matches the selected-v1 report: **2,048 India / 2,952 US / 291 singletons**.

These parity checks strongly support that the audit reconstructed the same anchor windows as production evaluation code.

## Results

### Headline population and evaluation slices

| Slice | N | India share | Singleton rate | Mean truth cardinality | Largest audited proportion deviation | Largest mean SMD |
|---|---:|---:|---:|---:|---|---:|
| Full train population | 2,206,821 | 40.0208% | 5.5848% | 3.4613 | reference | reference |
| Development 30k | 30,000 | 39.8233% | 5.5333% | 3.4665 | card=2: +0.381 pp, z=1.77 | 0.0070 |
| Fit fold | 17,990 | 39.8777% | 5.3029% | 3.4636 | card=2: +0.507 pp, z=1.82 | 0.0076 |
| Early-stop fold | 4,570 | 39.5405% | 5.5799% | 3.4803 | US share: +0.480 pp, z=0.66 | 0.0178 |
| Calibration fold | 4,389 | 39.9635% | 5.7416% | 3.4805 | card=3: -1.202 pp, z=-1.86 | 0.0185 |
| Development holdout | 3,051 | 39.7247% | **6.5225%** | 3.4428 | card=3: -1.931 pp, z=-2.50 | 0.0213 |
| Confirmation 30k–35k | 5,000 | 40.1200% | 5.4800% | 3.4848 | card=5+: +0.778 pp, z=1.26 | 0.0190 |
| Confirmation 35k–40k | 5,000 | 40.9600% | 5.8200% | 3.4424 | India share: +0.939 pp, z=1.36 | 0.0180 |

The 30k development block, the calibration fold, and both confirmation windows are close to the full population on every audited aggregate. Absolute standardized mean differences for Source-1 name/address length and token-count means are below **0.022** in every slice, which is tiny.

Both raw Source-1 business name and address are nonempty for **100%** of training anchors. This says nothing about S2/S3 missingness, which is known to exist; it only removes Source-1 missingness as a possible composition confound here.

### The one material chance imbalance: India singletons in the small holdout

Full-population singleton rates are almost identical by country:

- US: **5.5828%**
- India: **5.5878%**

The 3,051-anchor development holdout contains **199 singletons (6.5225%)**, versus about **170.4** expected at the full-population rate, an excess of ~28.6 anchors.

That excess is almost entirely India:

- holdout US: **102 / 1,839 = 5.5465%**, only -0.036 pp from population US;
- holdout India: **97 / 1,212 = 8.0033%**, **+2.415 pp** versus population India;
- under the hash-random reference approximation, the India singleton deviation is **z = 3.66**;
- population expectation for 1,212 India anchors is ~**67.7** singletons, so the holdout contains ~**29.3** extra India singletons.

This is not evidence that the hash protocol is systematically biased. It is a localized random imbalance in a small slice, exactly the sort of thing that happens when humans insist on extracting cosmic meaning from a few thousand rows.

The two confirmation windows do **not** show the same India imbalance:

| Slice | US singleton rate | India singleton rate |
|---|---:|---:|
| Full population | 5.5828% | 5.5878% |
| Calibration | 5.7685% | 5.7013% |
| Holdout | 5.5465% | **8.0033%** |
| Confirmation 30k–35k | 5.5110% | 5.4337% |
| Confirmation 35k–40k | 6.0976% | 5.4199% |

The combined 10,000 already-consumed confirmation anchors are also close to population overall: **40.54% India**, **5.65% singletons**, mean truth cardinality **3.4636**.

## Interpretation

1. **No evidence of broad sample-composition bias.** The main 30k development population and both confirmation windows track the complete train-anchor population closely on country, cardinality, singleton prevalence, and Source-1 text shape.
2. **The selected-v1 5k confirmation score is not obviously flattered or depressed by the audited composition variables.** Its India share is modestly high (+0.94 pp), but singleton/cardinality/text-shape deviations remain small.
3. **The historical 3,051-anchor development holdout is a noisy India/singleton diagnostic.** Because India singletons are substantially overrepresented, a tiny score movement on that slice can reflect composition as much as a real modeling effect. The direction of score bias cannot be inferred without the model's row-level predictions: extra singletons help only when correctly left empty and hurt sharply when false-linked.
4. The existing India weakness and singleton false-positive problem remain real because they also appear on the independent 5k confirmation set. This audit does not explain them away.

## Red-team checks

- Complete S1 and truth files used; no sample substituted for population aggregates.
- IDs used only for deterministic sampling/fold reconstruction, never as model features.
- No S2/S3 records, candidate lists, matcher probabilities, or positive insertion involved.
- No threshold/model/candidate-cap tuning.
- No new confirmation/frozen holdout was consumed.
- Existing confirmation composition was checked only to validate already-consumed windows.
- Descriptive z-scores are not treated as leaderboard evidence or as proof of causal sampling bias.

## Risks / limitations

This audit tests observable Source-1 and truth-cardinality composition only. It cannot establish representativeness for retrieval difficulty, S2/S3 corruption patterns, candidate density, or matcher-score distribution without reading target inventories/candidates. Hash sampling should be pseudo-random with respect to business content, but one small slice can still have accidental imbalances, as the India singleton result demonstrates.

The standalone repository CLI uses DuckDB, which is already a pinned project dependency. The chat's base container does not expose that package and has no network access to install it; therefore the full empirical numbers above came from an equivalent vectorized analysis in the chat Python runtime. Helper logic was separately syntax/unit checked in the available container. The exact anchor-window parity against committed confirmation reports is the stronger end-to-end reconstruction check.

## Recommendation

**PROMOTE** the current hash-based development/confirmation sampling protocol as compositionally sound for continued experiments, with one operational rule:

> Do not promote or reject tiny India/singleton gains based only on the 3,051-anchor development holdout. Require the standard calibration protocol plus a larger independent/paired check, and always report country + singleton/cardinality slices.

A useful integration follow-up is to have the standard benchmark emit this compact composition fingerprint automatically, so future slice drift is visible without consuming any new holdout.
