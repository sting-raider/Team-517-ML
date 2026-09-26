# M001a — IDF-weighted token similarity feasibility

**Issue:** #262  
**Branch:** `agent/m/M001a-idf-pair-feasibility`  
**Recommendation:** **PROMOTE-EMPIRICAL-GATE**

## Hypothesis

The selected matcher already has unweighted token Jaccard/overlap/coverage features, but those features treat losing a highly distinctive token the same as losing a ubiquitous token when token counts are otherwise matched. Country/field-local inverse document frequency may expose useful evidence that is currently collapsed, especially for the weaker India slice.

This task is a bounded feasibility prerequisite to backlog P0 M001. It asks whether the weighting has enough practical dynamic range on the supplied corpus to justify a full train/inference implementation and same-candidate INT003 ablation. It does **not** claim a competition-score gain.

## Change

No production model, feature schema, retrieval path, threshold, or submission behavior changed.

Added:

- `tools/experiments/m001a_idf_pair_feasibility.py`
- `tests/test_m001a_idf_pair_feasibility.py`
- aggregate JSON and this report

The helper defines a reusable weighted analogue of the current token-overlap family:

- weighted Jaccard;
- weighted overlap/containment;
- weighted left coverage;
- weighted right coverage.

For token (t), the feasibility weight is:

[
w(t) = \log\left(\frac{N_{country}+1}{df_{country,field}(t)+1}\right)+1.
]

The +1 floor keeps even common tokens positive. Similarity scores remain in [0,1].

## Protocol

### Data

Complete supplied `train_source1.tsv`, no sampling:

- **2,206,821** Source-1 anchors
- US: **1,323,633**
- India: **883,188**

No train/test S2/S3 text, ground-truth labels, confirmation/frozen holdout, France labels, external entity data, or leaderboard feedback were used.

The helper ignores entity IDs as evidence. Country is used only to partition document-frequency profiles, not as a match predictor.

### Normalization and tokens

The experiment uses a Python semantic mirror of repository normalization:

1. Unicode NFD decomposition;
2. remove combining marks;
3. lowercase;
4. preserve Unicode letters/numbers;
5. collapse other characters to separators.

Token sets are all normalized whitespace-delimited tokens, including numeric tokens. This matches the broad token-set semantics of the existing pair-overlap feature more closely than F007a's blocker-specific length/stopword filters.

Country + field-local Source-1 DF was measured over the **complete population** before any probes.

Population token census:

| Country | Name vocab | Address vocab | Name postings | Address postings |
|---|---:|---:|---:|---:|
| US | 70,685 | 148,006 | 4,582,815 | 7,785,716 |
| India | 50,639 | **321,044** | 3,265,499 | **10,235,906** |

### Controlled deletion probe

For every row/field with at least two unique tokens:

1. identify the lowest-DF token;
2. identify the highest-DF token;
3. compare the original text token set to a variant deleting the rare token;
4. compare the same original set to a variant deleting the common token.

Both variants remove exactly one token from the same original set. Therefore ordinary unweighted set Jaccard is exactly ((k-1)/k) for both. Any score separation comes solely from token weighting, not token count or edit size.

This is deliberately mechanistic. It is not presented as a natural corruption model or positive-pair benchmark.

## Results

### Coverage

The probe applies to almost the entire population:

| Country | Field | Eligible rows | Coverage | Nonuniform DF among eligible |
|---|---|---:|---:|---:|
| US | name | 1,309,023 | 98.8962% | 99.9936% |
| US | address | 1,323,633 | 100.0000% | 100.0000% |
| India | name | 883,165 | 99.9974% | 99.9928% |
| India | address | 883,188 | 100.0000% | 100.0000% |

So this is not a niche feature that only activates on a tiny long-tail slice.

### Rare-token loss vs common-token loss

The primary statistic is:

[
\text{gap} =
\text{weighted-similarity(common-token deleted)}
-
\text{weighted-similarity(rare-token deleted)}.
]

Positive values mean the IDF representation penalizes loss of rare evidence more strongly.

| Country | Field | Mean gap | Median gap | p90 gap | Share gap ≥ 0.10 |
|---|---|---:|---:|---:|---:|
| US | name | **0.218688** | 0.212400 | 0.372864 | 82.2775% |
| US | address | **0.199911** | 0.199039 | 0.259469 | 99.2534% |
| India | name | **0.324002** | **0.324778** | 0.471732 | **95.0996%** |
| India | address | **0.137302** | 0.130386 | 0.192493 | 81.9393% |

For every eligible probe, the corresponding **unweighted score gap is exactly 0**.

The effect is strongest on Indian business names. The current unweighted token-set view cannot distinguish the two matched perturbations at all, whereas IDF weighting produces a median separation of about **0.325**.

### How different are the tokens?

Median document frequencies of the selected rare/common token:

| Country | Field | Rare token median DF | Common token median DF |
|---|---|---:|---:|
| US | name | 457 | 55,307 |
| US | address | 66 | 220,848 |
| India | name | **136** | **521,781** |
| India | address | **18** | 215,082 |

The average fraction of total row token weight carried by the selected token also differs sharply:

| Country | Field | Rare-token weight share | Common-token weight share |
|---|---|---:|---:|
| US | name | 0.4163 | 0.1976 |
| US | address | 0.2781 | 0.0782 |
| India | name | **0.4673** | 0.1433 |
| India | address | 0.1769 | 0.0396 |

This confirms that the measured separation is not driven by a tiny number of outliers. The corpus has substantial within-row token-discriminativeness variation.

## Validation / red team

Executed in the available private Python runtime:

- five authored semantic checks: **PASS**
  - normalization/tokenization;
  - exact/empty semantics;
  - rare-token deletion penalty;
  - uniform-weight scaling invariance and [0,1] bounds;
  - IDF positivity/monotonicity;
- 10,000 deterministic randomized set/weight cases:
  - weighted Jaccard and overlap symmetry: **PASS**
  - directional coverage swap identity: **PASS**
  - [0,1] bounds: **PASS**
- matched unweighted deletion-gap sanity: **0 exactly** for all eligible population probes.

No label, confirmation, or record-ID leakage exists in this experiment because those inputs are not used.

## Runtime

The chat execution surface has a per-call limit, so the reproducible full audit was executed as four bounded complete-file passes:

- US DF census: 30.05 s
- India DF census: 32.93 s
- US population probes: 45.37 s
- India population probes: 44.12 s
- total measured Python time: **152.47 s**

No sample substitute was used.

## Interpretation

M001a answers one narrow question: **is there enough corpus-frequency dynamic range for IDF weighting to encode evidence that the existing unweighted overlap features necessarily erase?**

Yes.

That answer is particularly relevant to India. The largest separation occurs in Indian names, while prior work shows India is the weaker end-to-end slice. This does not establish that the feature will improve India F0.5, but it makes a real same-candidate matcher ablation worth the engineering cost.

The result also complements F007a: F007a showed that India has unusual token-frequency structure and abundant rare address vocabulary. M001a now shows that those frequency differences can materially change pairwise evidence under a controlled equal-edit perturbation.

## Risks and limitations

1. **Source-1 DF is a feasibility proxy.** A production pair feature must define train/inference-safe token profiles for the complete target inventory, not silently reuse Source-1 frequencies.
2. **The deletion probe is synthetic.** It proves representational sensitivity, not that authentic positive pairs lose rare tokens at a useful rate.
3. **Numeric overlap exists.** All tokens are included, so some signal may overlap with M003 rare-number commonness work. A full gate should ablate lexical-only vs all-token weighting if the combined feature family becomes too redundant.
4. **No target-side score claim.** Candidate recall, blocking oracle, singleton FPR, macro F0.5, and France accuracy are unmeasured here.
5. **Normalization parity.** Python NFD mark removal is a semantic mirror rather than byte-for-byte DuckDB `strip_accents()` parity for every Unicode edge case.

## Recommendation

**PROMOTE-EMPIRICAL-GATE.**

The next M001 experiment should be one variable:

- keep the current INT003 fused cap-160 candidates unchanged;
- build country/field-local token DF profiles from the permitted complete train inventory, with the exact same construction available on test inference inventory;
- append a compact IDF-weighted token-overlap block to the 57-feature matcher;
- train the same depth-10 CatBoost on the same fit/early/calibration folds;
- calibrate only on the existing calibration set;
- report official macro F0.5, India/US, singleton FPR, threshold, candidate recall/oracle parity, runtime/memory, and paired anchor deltas;
- if combined with M003/M009, first test M001 alone so attribution remains possible.

Do not promote the feature to production from this Source-1 feasibility result alone.
