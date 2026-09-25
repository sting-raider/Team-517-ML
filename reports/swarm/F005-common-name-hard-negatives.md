# F005 — Common-name / different-address hard-negative audit

**Issue:** #15  
**Branch:** `agent/r/F005-common-name-hard-negatives`  
**Recommendation:** **FOLLOW-UP**  
**Code checkpoint:** `8d2cc28c53a956c62564b14780bdc5381bb2295c`

## Hypothesis

Repeated/common normalized source-one business names create a concentrated hard-negative family: different real businesses share the same name but are separated by address evidence. If this family is common, especially in India, the matcher should know when a name is nondiscriminative and hard-negative mining should deliberately include same-name/different-address examples.

A secondary hypothesis was that source-one name ambiguity might be especially common among true singletons and therefore help the singleton gate.

## Protocol

This was a **full-data audit, not a sample**.

Inputs from the connected challenge Drive:

- `train_source1.tsv`: 210,069,713 bytes; **2,206,821** source-one anchors.
- `train_ground_truth.tsv`: 127,015,583 bytes; **2,206,821** truth rows.
- Countries: US and India only, as expected for labeled training data.

The chat runtime streamed the complete source-one TSV in 200k/250k-row chunks. The primary grouping key was:

`(country, normalized_business_name)`

Normalization followed the repository semantics: lowercase, accent stripping, replace non-letter/digit runs by spaces, trim. All **2,206,821 business-name rows were ASCII**, so the executed Python NFKD parity implementation is exact for name grouping under this dataset. Only **554 address rows (0.0251%)** contain non-ASCII characters; address-number extraction is unaffected by accents. The durable helper committed in this branch uses the exact DuckDB normalization expression from `src/ber/data.py`.

For every repeated normalized-name group, the audit computed:

- anchors in the group;
- unordered same-name pair count;
- exact normalized-address equality;
- first-address-number agreement/conflict when both rows expose a number;
- exact address-token Jaccard bands for every unordered pair;
- name-frequency bucket;
- singleton vs non-singleton collision rates using the full ground-truth file.

No row-level business records or names are committed.

Durable reproduction command:

```bash
python -m ber.common_name_audit \
  --source1 /path/to/train_source1.tsv \
  --truth /path/to/train_ground_truth.tsv \
  --output artifacts/f005_common_name_audit.json
```

The current ChatGPT container did not have the repository's `duckdb` wheel installed, so the committed helper was syntax-checked with `py_compile` but not re-executed here. The measurements below come from the independently executed full-file chunked audit described above.

## Baseline / normalization effect

A minimal lowercase+trim grouping already places **845,414 / 2,206,821 = 38.3091%** of anchors in a repeated-name group.

Repository-style punctuation/spacing normalization raises that to **866,141 / 2,206,821 = 39.2484%**, an increase of **20,727 anchors (+0.9392 percentage points)**.

Therefore the ambiguity is not mainly created by aggressive normalization. Most of it is present in the original names.

## Results

### Collision prevalence

| Slice | Source-one anchors | Repeated-name groups | Anchors in repeated-name groups | Collision rate | Same-name pairs | Max name frequency |
|---|---:|---:|---:|---:|---:|---:|
| All | 2,206,821 | 180,744 | 866,141 | **39.2484%** | 8,869,036 | 253 |
| US | 1,323,633 | 112,151 | 474,025 | **35.8124%** | 5,515,514 | 253 |
| India | 883,188 | 68,593 | 392,116 | **44.3978%** | 3,353,522 | 99 |

India's collision-row rate is about **24.0% higher relatively** than the US rate (44.40% vs 35.81%). This is a plausible contributor to India's harder precision regime, but this audit does not prove causality for current model errors.

### The same-name pairs are overwhelmingly different locations

Across all **8,869,036** unordered same-normalized-name pairs:

- **8,869,036 (100%)** have different normalized addresses.
- **0** have the same non-empty normalized address.
- **8,324,084** pairs have a first address number on both sides.
- **8,288,072 / 8,324,084 = 99.5674%** of number-comparable pairs have conflicting first numbers.

By country:

| Slice | Number-comparable same-name pairs | First-number conflicts | Conflict rate |
|---|---:|---:|---:|
| US | 5,515,514 | 5,512,944 | **99.9534%** |
| India | 2,808,570 | 2,775,128 | **98.8093%** |

This is strong evidence that exact/common business names frequently identify different branches or businesses and that address evidence must override name equality when it conflicts.

### Address-token overlap

Exact pairwise token Jaccard was computed for all 8,869,036 same-name pairs.

| Address token Jaccard | Pair count | Share |
|---|---:|---:|
| zero overlap | 6,327,208 | **71.3404%** |
| (0, 0.25] | 2,524,731 | **28.4668%** |
| (0.25, 0.50] | 16,951 | 0.1911% |
| (0.50, 0.75] | 143 | 0.0016% |
| (0.75, 1] | 3 | <0.0001% |

So **99.8072%** of same-name pairs have address-token Jaccard at or below 0.25.

The country shapes differ:

- US: **80.68%** zero address-token overlap.
- India: **55.97%** zero overlap, with **43.67%** in (0, 0.25].

India therefore has more low-but-nonzero address lexical overlap inside same-name hard-negative families. That makes simple "any address token matches" rules particularly unsafe there.

### Pair burden is concentrated in high-frequency names

| Name frequency | Groups | Anchors | Same-name pairs |
|---|---:|---:|---:|
| 2 | 100,854 | 201,708 | 100,854 |
| 3–5 | 54,318 | 193,520 | 262,745 |
| 6–20 | 17,531 | 144,445 | 582,823 |
| 21–100 | 7,932 | 312,337 | 6,920,820 |
| >100 | 109 | 14,131 | 1,001,794 |

Only **8,041 / 180,744 = 4.45%** of repeated-name groups have frequency above 20, but they create **7,922,614 / 8,869,036 = 89.33%** of the pair burden.

This makes high-frequency exact-name groups an efficient hard-negative mining target. Exhaustively mining every repeated-name pair is unnecessary.

### Singleton test: negative result

The name-collision flag is **not** a useful standalone singleton prior.

| Slice | Class | Anchors | Collision anchors | Collision rate |
|---|---|---:|---:|---:|
| All | singleton | 123,247 | 48,382 | **39.2561%** |
| All | non-singleton | 2,083,574 | 817,759 | **39.2479%** |
| US | singleton | 73,896 | 26,335 | 35.6379% |
| US | non-singleton | 1,249,737 | 447,690 | 35.8227% |
| India | singleton | 49,351 | 22,047 | 44.6739% |
| India | non-singleton | 833,837 | 370,069 | 44.3815% |

Overall the difference is only **+0.0082 percentage points** for singletons. Do **not** promote source-one common-name status by itself as a singleton gate.

## Error analysis / mechanism

The dominant hard-negative family is not "slightly different spelling of the same address." It is the opposite: **identical normalized name, sharply different location evidence**.

Three mechanisms matter:

1. **Exact name is often nondiscriminative.** The current blocker gives an exact normalized-name key a large retrieval bonus. That is useful for recall, but exact-name equality should not be treated as decisive matching evidence when the name is common.
2. **Address-number conflict is extremely strong inside this family.** More than 99.5% of comparable same-name pairs disagree on the first address number. Current matcher features already include number conflict, so the next question is whether training exposes enough of these negatives and whether common-name frequency lets the model weight the conflict correctly.
3. **India is more ambiguous.** A larger fraction of Indian anchors share names, and Indian same-name addresses more often have a little token overlap rather than none. This can make weak address-overlap evidence look deceptively positive.

## Interaction with current pipeline

The current blocker includes a full normalized-name key with bonus 50 and retains keys with inventory frequency up to 1000. The current 47-feature matcher includes string similarities, token overlap, number agreement/conflict, retrieval score, key-hit count, and source, but **does not contain an explicit name-frequency/commonness feature**.

This audit therefore points to a concrete missing signal: the model cannot directly distinguish "exact name shared by 2 records" from "exact name shared by 100+ plausible businesses" except indirectly through retrieval score.

## Risks / checks

- **No label or ID leakage:** entity IDs were used only to join source-one rows to their own ground-truth cardinality; IDs were never treated as predictive evidence.
- **No external identity data:** only supplied challenge files were used.
- **No split contamination claim:** this is a corpus forensic audit, not a model fit or holdout score.
- **No F0.5 claim:** source2/source3 candidates and predictions are not part of this experiment, so changing official macro F0.5 is not asserted.
- **Normalization parity:** source-one names are entirely ASCII, making the executed name grouping equivalent to repository punctuation/case normalization. Only 554 addresses are non-ASCII; this is too small to alter the main conclusions but exact address-token counts should be reproduced with the committed DuckDB helper before using tiny deltas.
- **Current candidate errors not directly linked:** this audit identifies a large plausible hard-negative family but does not show how many current CatBoost false positives fall inside it. That requires candidate/prediction artifacts.

## Interpretation

**Hypothesis supported for hard-negative structure; singleton sub-hypothesis rejected.**

Same-name/different-address negatives are a major structural property of the training corpus, particularly in India. The pair burden is extremely concentrated in a small number of high-frequency names, making targeted hard-negative mining cheap and high-information.

However, common-name status alone is essentially independent of truth singleton status. It should be used as **candidate ambiguity evidence**, not as an anchor-only "predict empty" rule.

## Recommendation: FOLLOW-UP

Highest-value next experiment:

1. Add an explicit, label-free **normalized-name frequency/commonness feature** (anchor and/or target inventory frequency, plus an exact-name-commonness interaction with address/number conflict).
2. Mine hard negatives preferentially from frequency >20 same-name groups, with country-balanced sampling so the enormous US pair mass does not drown India.
3. Evaluate on the exact current development benchmark with unchanged candidates first. Report macro F0.5, India/US, singleton FPR, and especially false positives where name is exact but address number conflicts.
4. Separately measure how many current CatBoost false positives are members of this F005 family before changing blocker bonuses. Do not weaken exact-name retrieval purely from this corpus audit; that could lose recall.

No direct model change is promoted from F005 alone.
