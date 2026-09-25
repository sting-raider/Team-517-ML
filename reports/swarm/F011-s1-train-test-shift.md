# F011 — Full Source-1 US/India train-test shift audit

**Issue:** #49  
**Branch:** `agent/r/F011-s1-train-test-shift`  
**Recommendation:** **FOLLOW-UP**  
**Primary upstream census:** X001 PR #32, head `164c2694e3b0006c4e8f5917215cb966add6c053`

## Hypothesis

Unlabeled Source-1 train→test distribution shift within US and India may be large enough to perturb blocker density or matcher calibration. If the within-country text format changes materially, country-specific normalization or representation work is justified. If the within-country format is stable but the country mixture changes, calibration / weighting is the higher-value follow-up.

## Change

No production retrieval, feature, matcher, threshold, or scorer behavior changed.

This task computes an explicit train-vs-test shift analysis from a previously completed **full-file Source-1 census** on the exact challenge TSVs. The input census was produced by X001 from all 2,206,821 training S1 anchors and all 1,732,544 test S1 anchors, with no sampling. F011 adds paired train/test deltas, country-mixture analysis, and a calibration-sensitivity diagnostic.

The complete `train_source1.tsv` (210,069,713 bytes) and `test_source1.tsv` (175,022,086 bytes) were also streamed into this chat successfully. An independent raw-file rescan could not be launched because every available Python/container backend returned platform session-capacity errors (`TooManyActiveSessions` / `ClientError`). No sampled substitute was used.

## Protocol

Sources:

- main `reports/data_audit.json` for canonical S1 record counts and mean lengths;
- X001 aggregate artifact `reports/swarm/X001-france-source1-audit.json` at PR #32 head `164c2694e3b0006c4e8f5917215cb966add6c053`;
- main `reports/RESULTS.md` for the selected confirmation country scores.

Cross-check: X001 full-file counts exactly match main's independent data audit:

| Split | US | India | France |
|---|---:|---:|---:|
| Train S1 | 1,323,633 | 883,188 | 0 |
| Test S1 | 663,106 | 809,986 | 259,452 |

Measured S1 fields reused from X001: mean characters, non-ASCII rate, NFKD diagnostic-fold change rate, hyphen rate, apostrophe rate for business name and address. X001 used the complete S1 files. NFKD is only an accent-sensitivity diagnostic proxy; production normalization remains DuckDB `strip_accents()`.

F011 calculations are deterministic arithmetic over those aggregate counts/rates. No labels, record IDs, leaderboard feedback, or external business data enter the shift calculation.

## Baseline context

Current selected confirmation performance:

- macro F0.5: **0.928835**
- US: **0.948339**
- India: **0.900722**
- candidate pair recall at cap 640: **0.947246**
- blocking oracle macro F0.5: **0.980951**

These scores are context only. F011 does not rerun the matcher and does not claim a new F0.5.

## Results

### 1. Within-country Source-1 format is extremely stable

Test minus train deltas:

| Metric | US delta | India delta |
|---|---:|---:|
| Mean name chars | -0.001800 | -0.011534 |
| Mean address chars | +0.003685 | +0.014211 |
| Name hyphen rate | -0.030166 pp | -0.003630 pp |
| Name apostrophe rate | +0.038396 pp | +0.000390 pp |
| Address non-ASCII rate | +0.000000 pp | -0.005319 pp |
| Address hyphen rate | +0.009127 pp | **+0.152428 pp** |
| Address apostrophe rate | +0.001040 pp | +0.005537 pp |

US names/addresses remain entirely ASCII in both splits in the X001 census. India name non-ASCII remains zero; India address non-ASCII changes only from 0.062727% to 0.057408%.

The largest observed absolute within-country rate change is India address hyphen usage at **+0.1524 percentage points**. Mean string lengths move by less than **0.015 characters** in either country.

On the measured S1 dimensions, there is no evidence of a meaningful US/India formatting regime change between train and test.

### 2. The major seen-country shift is mixture, not format

Training S1 country mix:

- US: **59.9792%**
- India: **40.0208%**

Among test anchors restricted to the two seen countries:

- US: **45.0146%**
- India: **54.9854%**

So India gains **+14.9646 percentage points** of the US/India mixture, while US loses the same amount.

Across the full test S1 population:

- US: **38.2735%**
- India: **46.7513%**
- France: **14.9752%**

This is a material deployment-mixture shift even though the measured US and India S1 text formats themselves are nearly stationary.

### 3. Calibration-sensitivity diagnostic

As a deliberately simple counterfactual, hold the measured confirmation country scores fixed:

- US F0.5 = 0.948339
- India F0.5 = 0.900722

Weighting those fixed conditional scores by the training S1 US/India mix gives **0.929282**. Weighting the same fixed scores by the seen-country test S1 mix gives **0.922157**, a difference of **-0.007126 macro F0.5**.

This is **not a test-score estimate**. It excludes France, assumes country-conditional performance is unchanged, ignores S2/S3 distribution changes, and does not model threshold/calibration interactions. It is only a sensitivity calculation showing that the observed country-mixture change is large enough to matter at competition scale because India is currently the weaker slice.

## Error analysis

The F011 hypothesis splits into two mechanisms:

1. **Within-country S1 format drift:** not supported by the measured dimensions. Length and punctuation/Unicode deltas are tiny.
2. **Population-mixture drift:** strongly supported. The seen-country test mix shifts from roughly 60/40 US/India to 45/55.

The biggest measured S1 formatting movement, India address hyphen usage (+0.1524 pp), is small relative to the existing US-vs-India performance gap (~0.0476 macro F0.5). Spending a P0 cycle on US/India Source-1 punctuation adaptation is therefore poorly motivated by this evidence.

The mixture result points instead toward country-balanced training/calibration, country-aware threshold sensitivity, or explicit evaluation under test-like country weighting. It also raises the value of India-specific precision work because India is both weaker and more prevalent in test than in training.

## Interpretation

**Within-country format-shift concern is rejected for the measured S1 features; calibration-mixture concern is supported.**

The current pipeline should not assume that train-weighted aggregate validation is representative of the test mixture. A model can have unchanged per-country behavior yet lose aggregate macro score when more anchors come from the weaker country slice.

This also means that future tiny aggregate gains should report country-stratified deltas and a test-mixture reweighted diagnostic. Otherwise an experiment can look positive simply because its evaluation slice has a friendlier US/India composition.

## Risks

- F011 reused the exact full-file aggregate census from X001 instead of independently rescanning raw rows because this chat's Python/container session backend was saturated. The record counts were cross-checked against main's independent `data_audit.json`, but tiny rate deltas are not an independent replication.
- Only a subset of S1 format metrics is available in the committed X001 aggregate artifact. Token-count, digit-pattern, and normalized-collision train/test deltas remain unmeasured here.
- S2/S3 files exceed the chat connector's 256 MiB transfer ceiling. Their train/test distribution shift could still alter candidate density and matcher calibration.
- The reweighting diagnostic is not a prediction of leaderboard or French performance.
- France has no labels; no French accuracy is invented.

## Recommendation

**FOLLOW-UP.**

Do **not** prioritize US/India Source-1 format-specific normalization changes based on this audit.

Prioritize a bounded decision/calibration experiment that evaluates the existing candidate/model outputs under:
1. ordinary development weighting,
2. country-balanced weighting, and
3. the observed US/India test S1 mixture,

while reporting US/India macro F0.5 and singleton FPR separately. This can determine whether global-threshold selection is sensitive to the deployment mixture without using any test labels.

When full S2/S3 execution is available on Modal or lossless shards, separately compare target-side candidate-count, retrieval-score, and key-hit distributions train→test; those are more direct calibration risks than the stable S1 formatting measured here.

## Follow-up tasks

- D005/D009 derivative: test-mixture-aware calibration sensitivity on existing labeled development outputs, with no new confirmation-window consumption.
- Target-side shift audit once full S2/S3 execution is available: candidate density / retrieval-score / key-hit distributions by country and source.
