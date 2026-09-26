# F014 — Composite numeric-text retrieval-key feasibility

**Issue:** #237  
**Pod:** R/F  
**Branch:** `agent/r/F014-composite-numeric-keys`  
**Recommendation:** **FOLLOW-UP**

## Hypothesis

F003a showed that address-number-only retrieval is broadly available but often too collision-prone in India and unseen France. The preregistered question was whether combining an address number with independent lexical evidence reduces Source-1 fanout enough, at useful enough coverage, to justify a full target-side R007 benchmark.

## Change

No production retrieval, matcher, threshold, or submission behavior changed.

Latest-main source inspection established that blocker v2/INT003 already contains three relevant composite families:

- `d:<first-address-number>:<address-word>`
- `h:<first-six-name-chars>:<first-address-number>`
- `z:<first-six-name-chars>:<last-address-number>`

Therefore F014 does **not** propose duplicating the existing `d:` family. It adds an analysis-only helper for an unmeasured alternative, first-address-number + full normalized name token, while reproducing production-style `d:` semantics for comparison.

## Protocol

The current chat verified and mounted the complete supplied Source-1 files from Drive:

- train_source1.tsv: 210,069,713 bytes
- test_source1.tsv: 175,022,086 bytes

A fresh raw rerun was attempted after both files were mounted. The private Python, visible Python, and container execution surfaces all failed at the session layer with `ClientError` before user code executed. No sample, partial scan, or fabricated count was substituted.

Rather than repeat already-completed work blindly, this report performs a bounded cross-experiment synthesis of two prior **complete-population** Source-1 audits on the same supplied files:

- F003a / Issue #23 / PR #191: country-local address-number document-frequency/selectivity census.
- X008 / Issue #147 / PR #156: exact production blocker-key-family survivability/collision census, including `d:/h:/z:`.

The synthesis compares the same practical Source-1 proxy cutoff, DF <= 1000. F003a's number-only statistic is deliberately generous: an anchor counts if **any** distinct address number has DF <= 1000. Production `d:` uses only the first address number but composes it with address words. That semantic mismatch favors the number-only comparator, so the observed composite rescue is conservative as a selectivity statement.

No ground-truth labels, S2/S3 records, confirmation/frozen holdout, leaderboard feedback, external business data, or record IDs as predictive evidence were used.

Current INT003 context only, not re-evaluated here: confirmation macro F0.5 0.950198, pair recall 0.944065, blocking oracle 0.980917.

## Results

### Existing production `d:` composition sharply reduces Source-1 collision burden

| Population | Number-only anchor coverage at DF<=1000 | Existing `d:` eligible-anchor rate at DF<=1000 | Difference |
|---|---:|---:|---:|
| train US | 75.1337% | 99.9992% | **+24.8655 pp** |
| train India | 30.8302% | 91.2494% | **+60.4192 pp** |
| test US | 85.4904% | 99.9991% | **+14.5087 pp** |
| test India | 32.8790% | 91.2419% | **+58.3629 pp** |
| test France | 24.2719% | 99.5722% | **+75.3003 pp** |

This is the main F014 result. The composite effect is especially large in the two regimes where F003a found number-only evidence weakest: India and France.

The comparison is not a candidate-recall experiment. It says that conjunction with lexical evidence can turn common numeric evidence into much lower-fanout Source-1 keys while preserving broad anchor coverage.

### France still contains many individually common `d:` keys, but usually has a rarer alternative

On test Source-1, the share of emitted `d:` key occurrences with proxy DF > 1000 is:

- US: **0.00%**
- India: **9.79%**
- France: **27.61%**

Yet anchors retaining at least one eligible `d:` key are 99.9991%, 91.2419%, and 99.5722%, respectively. France's maximum `d:` Source-1 proxy DF is 4,423 and India's is 8,968, so blindly treating every number+word composite as rare would still be wrong. The useful property is **within-anchor rare alternative availability**, not universal key rarity.

### Production name-prefix+number composites are already broadly selective in Source-1 proxy space

Test eligible-anchor rates:

| Country | `h:` eligible | `z:` eligible | max `h:` DF | max `z:` DF |
|---|---:|---:|---:|---:|
| US | 99.9569% | 99.9569% | 40 | 160 |
| India | 91.2655% | 91.2655% | 253 | 545 |
| France | 99.5803% | 99.5803% | 264 | 262 |

Every measured `h:/z:` Source-1 key remains below the proxy cutoff of 1000. This matters for the proposed number+full-name-token family: Source-1 fanout alone no longer provides a strong reason to add it. Its incremental value would have to come from **corruption complementarity**: cases where the six-character name prefix changes but another name token plus a number survives.

That is a positive-link/target-inventory question, not an anchor-frequency question.

## Error analysis / interpretation

1. **Composite lexical evidence works as intended.** The existing production `d:` family converts a weak number-only regime into broad low-fanout coverage, with the largest descriptive rescue in India and France.
2. **The repo already implemented the obvious address composite.** Adding another unconditional number+address-word family would duplicate existing evidence and likely add correlated scoring rather than new recall.
3. **The new name-token composite has an evidence boundary.** Existing `h:/z:` are already very selective in Source-1 proxy space. A number+full-name-token channel is justified only if it recovers true pairs missed because name prefixes are corrupted/reordered.
4. **France is not a label source.** Its large descriptive selectivity rescue supports conservative composite retrieval design but says nothing about correctness.
5. **Current residual error is not purely retrieval.** INT003's current confirmation oracle is 0.980917 versus actual 0.950198, so matcher/decision loss remains larger than the retrieval-ceiling loss. Any new retrieval family must earn its candidate-budget cost.

## Risks

- F003a and X008 are Source-1 DF proxies. Production blocker frequency is calculated on the full S2/S3 target inventory, which is unavailable in this chat because both raw files exceed the Drive connector's 256 MiB transfer limit.
- F003a's number-only baseline can use any address number; production `d:` uses the first address number. The comparison therefore is not a same-key ablation.
- The fresh F014 raw helper and focused tests could not be executed in this session because all compute surfaces returned a platform-level `ClientError`. They are preserved for recovery and must not be represented as passing.
- The Python helper mirrors DuckDB normalization with NFD accent folding. Prior F004R2 evidence found this mirror exact on the observed non-ASCII train-address rows, but it is not a formal equivalence proof for every Unicode code point.
- No pair recall, precision, candidate oracle, or macro F0.5 delta is claimed.

## Recommendation

**FOLLOW-UP**, but narrow R007 rather than adding generic numeric keys.

The next full-target experiment should first measure the marginal value of the **existing** `d:/h:/z:` families on the current INT003 candidate pipeline. Then test only genuinely complementary numeric probes, such as:

- first/all address number + surviving full name token when name-prefix evidence fails;
- additional distinct address numbers beyond first/last, DF-gated;
- source-specific frequency accounting for numeric composites.

Hold the final cap fixed. Required metrics: pair recall, entity recall, all-matches-retrieved rate, blocking-oracle macro F0.5, candidate-count quantiles, US/India and S2/S3 slices, marginal recovered/lost positives, runtime/memory, and recovered positives per added candidate.

Do **not** promote a new number+name-token family from Source-1 selectivity alone.

## Reproduction / handoff

Analysis helper:

```bash
python tools/experiments/f014_composite_numeric_keys.py \
  --source1 /path/train_source1.tsv --split train --countries US India \
  --out /tmp/f014-train.json

python tools/experiments/f014_composite_numeric_keys.py \
  --source1 /path/test_source1.tsv --split test --countries US India France \
  --out /tmp/f014-test.json

python -m unittest tests.test_f014_composite_numeric_keys -v
```

The helper is deliberately country-at-a-time internally to bound Counter memory. A recovery agent with a working compute session should execute it before citing the new number+full-name-token family. The already-reported `d:/h:/z:` findings above come from the completed full-population F003a/X008 measurements, not from an unexecuted F014 rerun.
