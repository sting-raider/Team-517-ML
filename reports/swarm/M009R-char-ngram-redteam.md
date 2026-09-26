# M009R — pairwise character n-gram feature red-team

## Hypothesis

M009 / PR #259 adds an opt-in eight-feature char-3/char-4 Jaccard + containment block but could not execute its Python tests. This red-team asks whether the authored implementation has a semantic/schema defect and whether its Python runtime is reasonable enough to justify the private same-candidate CatBoost gate.

## Scope and protocol

Stacked directly on M009 head `e0380d4054ec3dd06a50eee5fdec342fc3bc643c`. No challenge rows, labels, holdout, confirmation, France labels, external entity data, or record IDs are used.

Execution environment: CPython 3.13.5, NumPy 2.3.5, RapidFuzz 3.14.3.

1. Execute M009's five authored tests unchanged.
2. Independently recompute char n-gram sets with a simple reference implementation on 50,000 deterministic randomized name/address pairs containing ASCII, digits, whitespace, punctuation, accented characters, ligatures, German sharp-s, and combining accents.
3. Check pair symmetry and exact numeric agreement.
4. Exercise the legacy `features()` function on 5,000 randomized rows and require width 47 plus finite outputs.
5. Measure pure-Python runtime for legacy47 and char8 on the same 20,000 synthetic records. This is a Tier-1 microbenchmark, not production throughput.

## Results

**Functional validation: PROMOTE to empirical gate.**

- Authored M009 tests: **5/5 PASS** in 0.001 s.
- Independent randomized oracle: **50,000/50,000 PASS**, max absolute error **0.0**.
- Symmetry under left/right swap: **50,000/50,000 PASS**.
- Legacy randomized check: **5,000/5,000 PASS**, width remains exactly **47**, all values finite.
- Char batch output remains float32, eight columns, bounded in [0,1].

No normalization, missing-value, containment denominator, schema collision, determinism, or numerical-range defect was found.

### Runtime red-team

On the same 20,000 synthetic rows in one fresh CPython process:

| Block | Seconds | Rows/s |
|---|---:|---:|
| legacy 47 features | 1.0317 | 19,385 |
| M009 char 8 only | 1.1318 | 17,671 |

If naively computed serially, legacy+char would be about **2.10x** the legacy-only Python feature time on this synthetic batch. This comparison is conservative in the wrong direction for production: the selected pipeline can use the native `BER_FAST_FEATURES=1` path for the legacy block, while M009's new block is currently pure Python. Therefore integration must profile feature-generation wall time rather than assuming eight extra columns are cheap merely because eight is a small number humans find comforting.

The 50k-entry `compact_char_ngrams` LRU cache should help repeated Source-1 strings within anchor-grouped batches, so this microbenchmark must not be extrapolated directly to full training/inference wall time.

## Red-team checks

- `FEATURE_NAMES` stays 47 and is disjoint from the eight opt-in names.
- Existing `features()` and `batch_features()` code is unchanged by the PR; the char block requires explicit opt-in.
- Missing or too-short strings produce zero evidence rather than false exact-match evidence.
- Containment is symmetric because it divides by the smaller unique-gram set; randomized swap tests confirm this.
- Unicode code points are handled deterministically by Python slicing; this is not grapheme-cluster segmentation, but inputs are already repository-normalized and no functional inconsistency was observed.
- The primitive does not alter retrieval, candidate counts, or model schema until a caller explicitly appends it.

## Limitations

This red-team validates the primitive, not incremental predictive value. Compact edit ratio and Jaro-Winkler already encode related character evidence, so redundancy remains the main scientific risk. The private same-candidate depth-10 ablation is still required. A gain below 0.001 should be treated skeptically, and runtime must be reported alongside F0.5.

## Recommendation

**PROMOTE TO EMPIRICAL GATE.** M009's primitive is semantically sound and its previously unexecuted tests pass. Do not promote the features into INT003 by default yet. The private gate should hold cap160 candidates, folds, depth, seed, and all existing 57 features fixed; add only these eight columns, recalibrate threshold on the designated calibration fold, and compare macro F0.5, US/India, singleton FPR, paired anchor deltas, and feature-generation/training/inference runtime. Do not consume the frozen confirmation window for tuning.
