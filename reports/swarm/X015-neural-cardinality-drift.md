# X015 — Neural32 / blank-recovery prediction-cardinality transfer audit

## Recommendation

**PROMOTE-ROBUSTNESS / FOLLOW-UP.** The unlabeled output-cardinality evidence does **not** show the INT006/V5 neural32 system creating a new country-transfer red flag. Relative to INT003/V3, V5 moves the combined US+India test output toward the full labeled-train cardinality prior and moves France dramatically closer to the labeled US/India cardinality envelope. INT007/V6 adds a small amount of cardinality back; on France this slightly reverses V5's improvement, but V6 remains far closer to the labeled envelope than V3.

This is a robustness diagnostic, not an accuracy estimate. France has no supplied labels, and the committed V5 artifacts do not expose India and US output counts separately, so a per-country V5 India/US drift check remains a cheap follow-up.

## Hypothesis

The large INT006/V5 local F0.5 gain could still hide a pathological test-time set-size shift, especially on unseen France. If the output is at least structurally plausible, its predicted cardinality and empty-row rates should move toward, not farther from, the labeled US/India population priors without using France pseudo-labels.

## Protocol

Full supplied populations, no sampling:

- `train_source1.tsv`: 2,206,821 rows, SHA-256 `591af0e1dfeb65cab71ea6ee8cb69df00f92d6ba6fa79e05746c938775d14973`
- `train_ground_truth.tsv`: 2,206,821 rows, SHA-256 `70bc1d8a16c667e0155c2105d0ab2ebe41d7e7a85d8a529e3ca81c6c3a5af037`
- `test_source1.tsv`: 1,732,544 rows, SHA-256 `3d4a32c54c2ca9c53fd7c2be105bf26f708f94c4d2f88eb370972a195665c2f5`

The helper independently rescans train Source-1 + truth to recover country-conditioned truth cardinality and singleton priors, and test Source-1 to recover country counts. It then consumes only committed aggregate output artifacts from PR #268:

- `reports/int003_test_country_drift.json`
- `reports/neural32_submission.json`
- `reports/neural32_france_prediction_audit.json`
- `reports/blank_recovery_submission.json`

No test labels, France pseudo-labels, candidate probabilities, threshold/model tuning, confirmation/frozen holdout, leaderboard feedback, external entity data, or record IDs as predictive evidence are used. IDs are used only to join supplied train truth to Source-1 country during the population census.

Command:

```bash
python tools/experiments/x015_neural_cardinality_drift.py \
  --train-source1 /path/train_source1.tsv \
  --ground-truth /path/train_ground_truth.tsv \
  --test-source1 /path/test_source1.tsv \
  --v3-country reports/int003_test_country_drift.json \
  --v5-submission reports/neural32_submission.json \
  --france-audit reports/neural32_france_prediction_audit.json \
  --v6-submission reports/blank_recovery_submission.json \
  --out reports/swarm/X015-neural-cardinality-drift.json
```

Measured full-scan runtime in this chat container: **12.08 s**. Focused tests: **4/4 PASS**.

## Population parity

The independent scan reproduces the established complete labeled population exactly:

| Slice | Anchors | Truth edges | Mean truth cardinality | Singleton rate |
|---|---:|---:|---:|---:|
| All train | 2,206,821 | 7,638,365 | 3.461253 | 5.584821% |
| US | 1,323,633 | 4,578,522 | 3.459057 | 5.582816% |
| India | 883,188 | 3,059,843 | 3.464543 | 5.587825% |

Complete test Source-1 counts also reproduce prior audits: **663,106 US**, **809,986 India**, and **259,452 France**.

For a fair seen-country comparison, the US/India train truth means are reweighted to the **test US/India mixture**. That reference is mean cardinality **3.462074** and singleton rate **5.585570%**. This avoids confusing a change in the US/India mixture with model drift.

## Result 1 — Seen-country combined cardinality moves toward the labeled prior

The committed V5 report does not contain India and US output totals separately, but exact **combined US+India** totals are derivable by subtracting the committed France counts from the complete V5 export receipt.

| Variant | US+India predicted edges | Mean matches / anchor | Gap vs test-mix train prior | Empty rate | Empty-rate gap vs prior |
|---|---:|---:|---:|---:|---:|
| V3 / INT003 | 4,688,562 | 3.182803 | -0.279270 | 6.359616% | +0.774046 pp |
| V5 / INT006 | 4,812,091 | 3.266660 | -0.195413 | 5.936085% | +0.350515 pp |
| V6 / INT007 | 4,831,436 | 3.279792 | -0.182281 | not reconstructible | not reconstructible |

V5 adds **123,529** predicted US+India edges relative to V3. That reduces the absolute seen-country mean-cardinality gap by **30.03%**. Its empty-rate gap shrinks by **54.72%**. V6 adds another **19,345** US+India links and reduces the mean-cardinality gap by **34.73%** relative to V3.

This direction agrees with the labeled-train prior and therefore does not expose a coarse seen-country cardinality regression. It does **not** prove the extra links are correct.

## Result 2 — France moves much closer to the labeled-country cardinality envelope

The labeled US/India truth means occupy the narrow range **[3.459057, 3.464543]**. Their singleton rates occupy **[5.582816%, 5.587825%]**.

| Variant | France edges | Mean matches / anchor | Distance above labeled mean range | Empty rate | Distance below labeled singleton range |
|---|---:|---:|---:|---:|---:|
| V3 / INT003 | 1,130,876 | 4.358710 | +0.894167 | 3.436088% | -2.146728 pp |
| V5 / INT006 | 931,003 | 3.588344 | +0.123801 | 4.617424% | -0.965392 pp |
| V6 / INT007 | 936,801 | 3.610691 | +0.146148 | not reconstructible | not reconstructible |

V5 removes **199,873** predicted France edges relative to V3. The distance of France's mean predicted cardinality from the labeled-country range falls by **86.15%**. The empty-rate distance falls by **55.03%**. This is a substantial label-free transfer sanity improvement.

V6 adds **5,798** France links, moving the mean from 3.5883 to 3.6107. That is a small reversal of V5's cardinality alignment, but V6 still leaves France **83.66% closer** to the labeled mean range than V3. Since the recovery rule was selected from labeled development behavior, this small drift is not by itself a reason to reject it.

## Result 3 — Overall averages are misleading because V5 changes countries in opposite directions

Across all test anchors, V3 emits 5,819,438 links and V5 emits 5,743,094, a net decline of **76,344**. That aggregate hides two opposite movements:

- US+India: **+123,529** links
- France: **-199,873** links

The all-country mean therefore falls from 3.358898 to 3.314833 even while the seen-country mean moves toward its labeled prior and France's extreme high-cardinality tail contracts. Country-conditioned diagnostics are the correct interpretation here.

V5's overall empty rate is 5.738613%, versus V3's 5.921812%. Again, this is descriptive only; a test empty row is not known to be a true singleton.

## Red-team checks

- Full population, no sampling: PASS.
- Source-1/truth one-to-one anchor coverage: 2,206,821 / 2,206,821; no missing truth anchor in Source-1.
- Train country/count and truth-edge parity with previous complete audits: PASS.
- Test country counts sum to 1,732,544: PASS.
- V3 per-country edges sum exactly to the committed 5,819,438 export edges: PASS.
- V3 per-country empty rows sum exactly to committed 102,598: PASS.
- V5 complete anchor count equals test Source-1 count: PASS.
- V6 country additions sum to committed total 25,143: PASS.
- No test labels or pseudo-labels were accessed.
- No threshold, dense prior, candidate cap, model, or decision rule was changed.

## Limitations and handoff

The main artifact gap is simple: `reports/neural32_submission.json` commits only total V5 matches/empty rows, while the France audit commits France-specific counts. This makes **combined US+India** exact but prevents an independent India-vs-US V5 output-cardinality split. A coordinator with the private V5 TSV or Modal volume should add two aggregate counters only: `{country: matches, empty_rows}`. No row-level artifact needs to leave the private volume.

V6 similarly reports added links by country but not how many previously empty rows became nonempty per country, so its country empty rates cannot be reconstructed from Git alone.

These are provenance/reporting gaps, not evidence of model failure. On the aggregate evidence that is committed, V5 is materially more plausible than V3 on both the labeled-country mixture and unlabeled France cardinality axes.
