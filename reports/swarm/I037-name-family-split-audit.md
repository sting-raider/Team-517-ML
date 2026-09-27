# I037 — normalized-name family dependence across INT003 splits

## Hypothesis

INT003 is anchor-ID disjoint, but the expanded fit population may place the same normalized Source-1 business-name families on both sides of fit and evaluation. If common, this is a validation-transfer dependency worth measuring even though equal names do not imply equal entities.

## Change

No model, blocker, feature, threshold, or split definition changed. A deterministic streaming audit reconstructs the current INT003 Source-1 hash ordering/folds and measures exact normalized-name-family sharing between fit and the early/calibration/holdout/consumed-confirmation populations.

## Protocol

- Complete train_source1.tsv: 2,206,821 anchors / 210,069,713 bytes; no sampling.
- Complete train_ground_truth.tsv: 2,206,821 truth rows / 127,015,583 bytes; labels used only for aggregate cardinality composition.
- Exact sample517: MD5 ordering through position 200,000 and fold517: SHA256 fold rule from src/ber/experiment.py.
- Current INT003 fit: dev positions <=30,000 assigned fit, plus fit-fold anchors at positions 50,001–200,000. Positions 45,001–50,000 are the already-consumed INT003 confirmation composition only; no model score is read or recomputed.
- Family key: lowercased, NFD accent/combining-mark removal, Unicode letters/numbers retained, separators collapsed. X002 established zero train-US/India business-name key change/collision difference between this NFD folded mirror and the folded production semantics.
- Primary overlap is same-country normalized-name family present at least once in fit. Empty normalized names are excluded from the overlap denominator.

Command:

    python tools/experiments/i037_name_family_split_audit.py --source1 /path/to/train_source1.tsv --truth /path/to/train_ground_truth.tsv --output reports/swarm/I037-name-family-split-audit.json
    python -m unittest tests/test_i037_name_family_split_audit.py

## Results

Reconstruction parity is exact for the committed INT003 populations: **108,115 fit**, **4,570 early**, **4,389 calibration**, **3,051 holdout**, and **5,000 confirmation** anchors. The 108,115 fit anchors contain 17,990 original dev-fit anchors plus 90,125 expanded fit anchors.

| Evaluation population | Core-fit family overlap | Current expanded-fit overlap | Added by expansion | Family-novel anchors |
|---|---:|---:|---:|---:|
| early | 5.580% | **15.689%** | +10.109 pp | 3,853/4,570 |
| calibrate | 4.466% | **15.448%** | +10.982 pp | 3,711/4,389 |
| holdout | 4.982% | **16.421%** | +11.439 pp | 2,550/3,051 |
| confirmation | 5.680% | **17.040%** | +11.360 pp | 4,148/5,000 |

The expanded fit therefore moves cross-split family exposure from roughly 4.5–5.7% to **15.4–17.0%**. This is material dependence, but it is not dominant: 83.0–84.6% of each evaluation population remains same-country-family novel.

### Country slices

| Population | India overlap | US overlap | India added by expansion | US added by expansion |
|---|---:|---:|---:|---:|
| calibrate | **19.954%** | 12.448% | +14.880 pp | +8.387 pp |
| holdout | **20.297%** | 13.866% | +14.851 pp | +9.190 pp |
| confirmation | **20.277%** | 14.842% | +14.441 pp | +9.268 pp |

India is consistently more exposed: about **20.0–20.3%** of calibration/holdout/confirmation anchors share a same-country normalized-name family with current fit, versus **12.4–14.8%** in the US. The expansion accounts for roughly 14.4–14.9 pp of India exposure.

### Family fanout and truth composition

Current fit has 96,918 distinct nonempty country+name families; 17,385/108,115 fit anchors (16.08%) belong to a repeated family. Among overlapping confirmation anchors, the number of same-family fit anchors has p50=2, p90=5, p99=9, max=13.

Confirmation family-overlap anchors have a higher high-cardinality (truth size >=5) share than family-novel anchors: **32.160% vs 26.663%** overall, and **33.659% vs 27.543%** in India. Singleton rates are 6.221% vs 5.039% overall. This composition difference means a raw overlap-vs-novel score comparison would need cardinality-aware interpretation rather than being treated as pure memorization evidence.

## Red-team checks

- Full Source-1 country totals reproduce the repository audit exactly: 1,323,633 US and 883,188 India.
- Calibration and holdout counts reproduce INT003 exactly; fit count reproduces the committed 108,115-anchor training population.
- Confirmation reconstructs exactly 5,000 anchors with 2,022 India / 2,978 US, matching the prior composition audit.
- Four focused deterministic tests pass for normalization, fold hashing, sample hashing, and overlap/cardinality accounting.
- A second complete-file run produced an identical aggregate payload after removing runtime fields (SHA256 abff4457f916e483d842640b332c448e3d3269c6fce95396fc831798604c3a8d).
- Name-only and same-country-name overlap differ by at most two anchors in these evaluation sets, so the finding is not driven by cross-country same-name collisions.

## Interpretation

This is **not direct label leakage**. Anchor IDs are disjoint, different Source-1 rows with the same normalized name are not assumed to represent the same business, and the current CatBoost does not ingest a raw name-family identifier as a categorical feature. The result instead establishes a measurable validation dependency: the expanded fit population exposes the model to business-name families that recur in later evaluation anchors, especially in India. Repeated businesses can share source-specific corruption or candidate structure, so a family-novel robustness slice is a useful stress test.

The dependency also does not invalidate the current INT003 score by itself. Most evaluation anchors remain family-novel, and the confirmation overlap slice is more high-cardinality than its novel slice, which is not an obviously easier population. Without candidate/model outputs on the same rows, assigning a score inflation number would be speculation.

## Risks

- The NFD normalizer is the same mirror used by X002, not a byte-for-byte DuckDB strip_accents implementation. X002 found no train-US/India business-name key change or collision inflation from that distinction, which bounds the practical risk for this audit.
- Exact normalized name is a conservative family definition. It misses related variants and legal-suffix variants, while common exact names can join unrelated businesses.
- No matcher probabilities or target inventory are used, so this task cannot determine whether family-overlap anchors score better or worse.
- The confirmation block is already consumed; its composition is descriptive only and must not be used for tuning.

## Recommendation

**PROMOTE-DIAGNOSTIC / FOLLOW-UP.** Add a same-country normalized-name-family-novel slice to the next development/holdout model comparison, using existing candidate/model artifacts where available. Keep the official entity-disjoint split as primary, but require gains to survive the family-novel slice, especially India. Do not reopen or tune on the consumed confirmation block. A future stricter group split can be used as a robustness test, not as a replacement for the official distribution unless evidence shows material score dependence.

Runtime for the first full pass was 22.76 s on this chat CPU; deterministic replication required another complete pass. No S2/S3 rows, external identity data, France labels, leaderboard feedback, or fresh confirmation scoring were used.
