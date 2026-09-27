# X014 — Unicode-preserving decomposition of the R029 France rare-word gate

**Issue:** #257  
**Branch:** `agent/x/X014-unicode-suffix-gate`  
**Recommendation:** **FOLLOW-UP — retain Unicode-preserving name/address variants as optional full-target R029 benchmark arms; do not treat accent folding as the dominant France residual.**

## Hypothesis

R029 reduced legal-suffix-stripped-name collision exposure sharply by conjoining the stripped name with a rare address word, but France retained a much larger Source-1 proxy collision rate (**1.8576%**) than US/India. X002 separately showed that accent folding destroys some French name/address distinctions.

The atomic question is whether R029's France residual is mainly caused by folding the stripped business name, folding the rare address word, or both.

## Change

No production retriever, matcher, threshold, model, or submission behavior changed.

This experiment evaluates four inference-safe Source-1 proxy views over exactly the same suffix-bearing query population:

1. folded stripped name + folded rare address word (exact R029 baseline);
2. folded stripped name + Unicode-preserving rare address word;
3. Unicode-preserving stripped name + folded rare address word;
4. Unicode-preserving stripped name + Unicode-preserving rare address word.

The folded view mirrors R029: NFKD decomposition, combining-mark removal, lowercase, then Unicode alphanumeric separator collapse. The Unicode view uses NFC + lowercase + the same separator collapse, without accent removal. The suffix family is unchanged.

Address words retain R029/F007a semantics: length >=3, nonnumeric, excluding the same address stoplist. The selected token is the lexicographic minimum `(country-local Source-1 DF, token)`, with DF <= 1000.

## Protocol

Complete supplied `test_source1.tsv`; **no sampling**.

- rows: **1,732,544**
- bytes: **175,022,086**
- SHA256: `3d4a32c54c2ca9c53fd7c2be105bf26f708f94c4d2f88eb370972a195665c2f5`
- US: 663,106 rows; 376,317 suffix-bearing queries
- India: 809,986 rows; 681,902 suffix-bearing queries
- France: 259,452 rows; 178,783 suffix-bearing queries

No Source-2/Source-3 sample was substituted. No labels, confirmation/frozen holdout, leaderboard feedback, external entity data, or record IDs as predictive evidence were used.

The standalone reproduction path is:

```bash
python -m unittest tests/test_x014_unicode_suffix_gate.py -v
python tools/experiments/x014_unicode_suffix_gate.py \
  --test-source1 /path/to/test_source1.tsv \
  --out reports/swarm/X014-unicode-suffix-gate.json
```

The live notebook execution was chunked only to stay below the per-cell runtime ceiling; every one of the 1,732,544 rows was processed. Measured compute across preprocessing, four full-spool views, and paired France diagnostics was approximately **206.9 s**. Focused validation: **5/5 tests PASS**.

## Baseline and parity

The folded/folded implementation reproduces R029 exactly for the collision metric on every country and reproduces its rounded coverage values within 1.2e-7 absolute.

| Slice | R029/X014 rare-word coverage | R029/X014 cross-original collision |
|---|---:|---:|
| US | 94.3359% | 0.085352% |
| India | 93.2892% | 0.055962% |
| France | 97.4058% | **1.857647%** |

Additional sanity checks:

- folded-vs-Unicode suffix detection differs on **0 rows** in all three countries;
- France fold-change rates reproduce X002 exactly: **15.7208% names**, **27.8314% addresses**;
- India address fold-change reproduces X002 at **0.0574%**; US has zero name/address fold changes.

This guards against obtaining an apparent improvement by silently changing the query population or R029 semantics.

## Results

### France decomposition

| Name view | Rare-word view | Coverage | Collision | Delta vs R029 | Relative collision change | Changed composite key | p99 group |
|---|---|---:|---:|---:|---:|---:|---:|
| folded | folded | 97.4058% | **1.85765%** | — | — | 0% | 2 |
| folded | Unicode | **97.7179%** | **1.82138%** | -0.03627 pp | -1.95% | 13.2189% | 2 |
| Unicode | folded | 97.4058% | **1.82836%** | -0.02929 pp | -1.58% | 8.9052% | 2 |
| Unicode | Unicode | **97.7179%** | **1.79218%** | **-0.06546 pp** | **-3.52%** | 20.9946% | 2 |

Both components contribute, with Unicode-preserving address words producing a slightly larger aggregate effect than Unicode-preserving names. The effects are roughly additive, but small: the combined view reduces France proxy collision from 1.85765% to 1.79218%.

Unicode-preserving rare words also increase coverage by **0.3121 pp**, from 174,145 to 174,703 covered France suffix rows. The p99 posting-group proxy remains 2 under every France view, so this is not a broad fanout collapse.

### US and India controls

US is **exactly invariant** across all four views: 94.3359% coverage, 0.085352% collision, p99 group 1.

India's coverage and collision are also invariant at report precision: 93.2892% coverage, 0.055962% collision, p99 group 1. Unicode-preserving address handling changes only **71** comparable India rare-word/composite keys, **0.01116%** of covered comparable queries, without changing aggregate collision exposure.

The effect is therefore France-specific in this supplied Source-1 population rather than a generic normalization perturbation.

## Paired France error analysis

For each of the 178,783 France suffix rows, status was paired as:

- 0 = uncovered;
- 1 = covered with no cross-original collision;
- 2 = covered and collision-exposed.

Against the folded/folded R029 baseline:

### Unicode address word only

- resolves **92** baseline collision-exposed rows (2->1);
- introduces **5** previously clean collisions (1->2);
- newly covers **558** rows: 524 clean, 34 collision-exposed;
- leaves 3,143 baseline collision rows collision-exposed.

### Unicode stripped name only

- resolves **51** baseline collision-exposed rows;
- introduces **0** new collisions;
- changes no coverage;
- leaves 3,184 collision rows collision-exposed.

### Unicode name + Unicode address word

- resolves **142** baseline collision-exposed rows;
- introduces **5** previously clean collisions;
- newly covers **558** rows: 525 clean, 33 collision-exposed;
- leaves **3,093** baseline collision rows collision-exposed.

The name-only variant is monotonic in this Source-1 collision proxy, while the address variant recovers more distinctions and coverage but changes the selected rare-token partition enough to create a small number of new collision groups.

A secondary identity check also shows that the folded baseline slightly understates accent-sensitive ambiguity: when folded groups are judged against Unicode-preserving original names, France collision exposure is 1.86339% rather than 1.85765%. The difference is only ~0.0057 pp.

## Interpretation

Accent folding is a measurable France-specific information loss, but it is **not the main cause** of R029's France residual collision burden.

The strongest Unicode combination improves the Source-1 proxy collision rate by only **0.06546 percentage points**, or **3.52% relative**, while more than 3,000 France suffix queries remain collision-exposed. The p99 group size does not move.

That makes the Unicode view useful as a low-risk complementary robustness channel, especially because US is unchanged and India is almost unchanged. It does not justify diverting the retrieval program around a France-specific normalization hypothesis as though it explains the current oracle ceiling.

## Metric boundary

This task intentionally does **not** report official macro F0.5, pair/entity recall, all-matches-retrieved rate, or blocking oracle. France has no labels, and the complete Source-2/Source-3 target files exceed this runtime's connector raw-file transfer ceiling.

The correct same-population baseline for X014 is therefore R029's folded/folded Source-1 selectivity proxy, which is reproduced exactly before comparing the Unicode variants.

The selected INT003 end-to-end confirmation remains separate evidence and was not re-scored or tuned here.

## Risks / red-team checks

- **Source-1 proxy only:** production posting frequencies and target collisions come from S2/S3. These results prioritize benchmark arms; they do not prove recovered positives.
- **No France accuracy claim:** coverage/collision of observable Source-1 keys is measurable; match correctness is not.
- **No hidden tuning:** no labels, confirmation anchors, frozen holdout, or leaderboard scalar affected the four-view choice.
- **No ID leakage:** entity IDs are not read into normalization, DF, key construction, or grouping.
- **Normalization parity:** exact R029 collision parity and X002 fold-change parity both pass before interpreting deltas.
- **Tiny effect skepticism:** the combined -0.06546 pp proxy collision change is small. It should not be promoted without a complete-target fixed-cap benchmark.

## Recommendation

**FOLLOW-UP.**

When complete S2/S3 retrieval compute is available, include a Unicode-preserving parallel R029 arm in the same fixed-cap experiment rather than replacing accent folding:

- current INT003 retrieval;
- + folded stripped-name / folded rare-word R029 probe;
- + Unicode name / folded rare-word probe;
- + Unicode name / Unicode rare-word probe.

Measure marginal pair/entity/all-match recall, blocking oracle macro F0.5, candidate-count quantiles, US/India slices, and runtime on identical anchors/cap. The name-only Unicode variant is particularly cheap to keep because it was monotonic in this proxy, while the full Unicode variant gives the largest France proxy reduction.

Absent a stronger target-side gain, prioritize larger retrieval-ceiling work over further micro-optimization of this France normalization effect.
