# R029 — Gate legal-suffix-stripped name probes with selective address evidence

**Issue:** #235  
**Branch:** `agent/r/R029-suffix-gated-probes`  
**Recommendation:** **FOLLOW-UP — promote the rare-address-word-gated probe to a full-target fixed-cap retrieval benchmark; do not deploy from this Source-1 proxy alone.**

## Hypothesis

F006a showed that removing legal-form suffixes from business names is far too collision-prone to use as an unconditional retrieval key. The narrower question is whether a stripped-name probe becomes selective enough to deserve a real S2/S3 benchmark when it is conjoined with independent address evidence.

The preregistered gates were:

1. stripped name + first normalized address number;
2. stripped name + the rarest eligible address word, using country/split-local Source-1 document frequency and the current blocker-style DF<=1000 cutoff;
3. stripped name + both the first number and rarest eligible address word.

## Change

No production retrieval, matcher, threshold, or submission behavior changed.

Added a dependency-free full-population audit helper that:

- mirrors F006a normalization and suffix stripping;
- mirrors F007a address-word eligibility: normalized nonnumeric tokens of length >=3, excluding the blocker address stoplist;
- computes country/split-local Source-1 address-word DF with per-record deduplication;
- indexes every Source-1 row under each proxy key, while evaluating coverage/collision burden only for suffix-bearing query rows. This matters because an unaffected row such as `Acme` must still contribute posting pressure when an `Acme LLC` query strips to `Acme`;
- writes only aggregate JSON. A temporary normalized row spool is deleted automatically.

Focused tests cover normalization/suffix semantics, F007a-style address words, rare-word DF/tie behavior, composite keys, cross-original collision accounting, and unaffected-row posting participation.

## Protocol

Data: complete supplied Source-1 populations, **no sampling**.

| Split | Rows | US | India | France |
|---|---:|---:|---:|---:|
| train | 2,206,821 | 1,323,633 | 883,188 | 0 |
| test | 1,732,544 | 663,106 | 809,986 | 259,452 |
| total | **3,939,365** | 1,986,739 | 1,693,174 | 259,452 |

Suffix-bearing query counts under the exact F006a suffix family are 751,958 US / 743,843 India in train and 376,317 US / 681,902 India / 178,783 France in test.

No Source-2/Source-3 rows were substituted with a sample. The live Drive connector still rejects the complete target files above 268,435,456 bytes, so R029 deliberately stops at a Source-1 selectivity/collision proxy. It does **not** claim candidate recall, blocking oracle, official macro F0.5, or France accuracy.

No labels, confirmation/frozen holdout, leaderboard feedback, record IDs as predictive evidence, or external business/entity data were used.

Reproduction:

```bash
python -m unittest tests/test_r029_suffix_gated_probes.py -v
python tools/experiments/r029_suffix_gated_probes.py \
  --train-source1 /path/to/train_source1.tsv \
  --test-source1 /path/to/test_source1.tsv \
  --out reports/swarm/R029-suffix-gated-probes.json
```

Validation: **6/6 focused tests PASS**.

Observed full-run wall time: **246.79 s**. Raw TSV normalization is performed once per split; method passes reuse a temporary normalized spool. Peak RSS observed during polling was about **0.76 GB**.

## Baseline parity

R029's stripped-name-only proxy exactly reproduces the published F006a collision-exposure rates after rounding to four decimals:

| Slice | F006a/R029 stripped cross-name collision rate |
|---|---:|
| train US | 38.9219% |
| train India | 50.3909% |
| test US | 31.1097% |
| test India | 49.8316% |
| test France | 45.1385% |

All five parity checks pass. This guards against obtaining a cleaner result by changing normalization or suffix semantics.

## Results

### Main comparison

`Coverage` is the share of suffix-bearing query rows that can emit the gated key. `Collision` is the share of covered query rows whose proxy posting group contains at least one *different* original normalized business name.

| Slice | Bare stripped collision | Number coverage / collision | Rare-word coverage / collision | Number+rare coverage / collision |
|---|---:|---:|---:|---:|
| train US | 38.9219% | 100.00% / 0.6418% | 86.52% / **0.1391%** | 86.52% / **0.00169%** |
| train India | 50.3909% | 91.28% / 7.6911% | 92.70% / **0.0573%** | 84.03% / **0.00352%** |
| test US | 31.1097% | 100.00% / 0.3324% | 94.34% / **0.0854%** | 94.34% / **0.00056%** |
| test India | 49.8316% | 91.27% / 7.2682% | 93.29% / **0.0560%** | 84.60% / **0.00312%** |
| test France | 45.1385% | 99.58% / 8.5955% | 97.41% / **1.8576%** | 97.01% / **0.05708%** |

The rare-word gate is the useful result. On India it reduces cross-name collision exposure from roughly **50% to 0.056%** while retaining about **93%** of suffix-bearing anchors. The train and test numbers are nearly identical, arguing against a one-split artifact.

France is harder: rare-word gating still cuts collision exposure from **45.14% to 1.86%** at **97.41%** coverage, but the residual rate is much higher than US/India. Adding the first address number reduces the France proxy collision rate further to **0.0571%** while retaining **97.01%** coverage.

### Posting-fanout proxy

Weighted p99 proxy group size among covered query rows:

| Slice | Bare stripped | Number | Rare word | Number+rare |
|---|---:|---:|---:|---:|
| train US | 286 | 1 | 1 | 1 |
| train India | 75 | 5 | 1 | 1 |
| test US | 149 | 1 | 1 | 1 |
| test India | 69 | 5 | 1 | 1 |
| test France | 294 | 6 | 2 | 1 |

Bare stripping has severe fanout. Number-only gating is much cleaner but still leaves meaningful India/France cross-name collisions. Rare-word gating makes the typical and p99 Source-1 proxy posting essentially singleton; only France reaches p99=2. Number+rare is p99=1 everywhere.

The positive incremental-fanout p99 versus the original normalized-name key falls from 222/61 on train US/India and 116/56/246 on test US/India/France under bare stripping to **0 for every rare-word and number+rare slice**.

### Rare-address-word selectivity

Among suffix-bearing rows covered by the rare-word gate, selected Source-1 DF is strongly country-dependent:

| Slice | selected rare-word DF p50 | p90 | share <=100 |
|---|---:|---:|---:|
| train US | 119 | 582 | 46.8% |
| train India | 16 | 305 | 75.7% |
| test US | 74 | 453 | 56.5% |
| test India | 15 | 298 | 76.5% |
| test France | 64 | 323 | 63.3% |

This agrees with F007a's earlier conclusion that India exposes unusually rich rare address vocabulary. It also explains why the rare-word gate preserves more India coverage than a number+rare gate: about 9% of Indian suffix-bearing addresses have no number, while the lexical gate remains available.

## Error analysis

1. **Bare stripping is independently re-invalidated.** R029 reproduces F006a's 31–50% collision exposure; there is no evidence to revisit an unconditional stripped-name union.
2. **Number-only is insufficient for India/France.** It keeps high coverage but still leaves 7.27% India and 8.60% France cross-name collision exposure on test. Common address numbers are not selective enough there.
3. **Rare-word gating is exceptionally clean on labeled-country proxies.** India train/test collision rates are 0.0573% / 0.0560%, with 92.70% / 93.29% coverage. US is also below 0.14%.
4. **France remains the transfer warning.** France rare-word collision is 1.86%, around 33x the India test rate despite still being vastly safer than bare stripping. The number+rare composite removes most of that residual burden.
5. **The strict composite costs India coverage.** Number+rare falls to about 84.6% India test coverage because the number gate is missing more often there. A full-target benchmark should therefore compare rare-word alone against number+rare, not assume the strictest key is globally best.

## Interpretation

F006a's suggested follow-up survives a much stronger feasibility test: **legal-suffix stripping can be made selective when the stripped name is conjoined with rare address lexical evidence.** The mechanism is especially promising for India, where current performance is weaker and rare address words are abundant.

This does not prove recovered positives. It only shows that the proposed probe is not doomed by the huge collision/fanout problem that killed bare stripping. The next question must be measured on the actual S2/S3 inventory: does the composite recover true links that INT003 misses, at fixed final cap and acceptable candidate cost?

For France, the Source-1 evidence favors including a stricter number+rare variant in that benchmark because rare-word-only residual collisions are visibly higher. That is a robustness hypothesis, not a France-label claim.

## Risks / red-team checks

- **Source-1 proxy limitation:** production retrieval DF/postings come from S2/S3. Source-1 selectivity can prioritize a target-side experiment but cannot establish target candidate count, recall, oracle, or F0.5.
- **Transductive scope:** DF is computed country/split-locally from the supplied Source-1 inventory only, with no labels. A production retriever must recompute equivalent target-side statistics rather than reuse these numbers.
- **Potential redundancy:** current INT003 character/lexical channels may already retrieve most links this key would find. Marginal recall, not raw coverage, is the promotion criterion.
- **France:** no labels exist. Collision/fanout is observable; match quality is not.
- **Normalization:** the stdlib normalizer is the same F006a path whose published collision rates are reproduced exactly at report precision. F004R2 separately found no mismatch against pinned DuckDB production semantics on all non-ASCII train Source-1 addresses.
- **No ID leakage:** entity IDs are never read into key construction or statistics.

## Recommendation

**FOLLOW-UP, with a strong promotion to full-target benchmarking.**

Do not deploy a stripped-name key directly. In a runtime with complete S2/S3, test at fixed INT003 cap160 on the established development/calibration anchors:

- current INT003 retrieval baseline;
- baseline + stripped-name + rare-address-word(DF<=1000);
- baseline + stripped-name + first-number + rare-address-word;
- optionally a stricter rare-word DF<=100 ablation if candidate pressure is still high.

Report pair recall, entity recall, all-matches-retrieved rate, blocking-oracle macro F0.5, candidate count quantiles, US/India slices, marginal recovered positives per added candidate, and runtime/memory. Preserve identical matcher/cap when evaluating retrieval-only effects.

No confirmation/frozen holdout should be consumed for this gate.
