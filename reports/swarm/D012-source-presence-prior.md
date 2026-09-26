# D012 — Source-presence priors from Source-1 evidence

## Hypothesis

Inference-safe Source-1 structure may predict whether an anchor has any Source-2 match, any Source-3 match, both-source support, or source-exclusive support even though D001a found no useful Source-1-only singleton signal. A stable held-out signal would justify soft source-aware priors in D004/D008 or expected-F0.5 decoding.

## Change

Recovered the stale BLOCKED D012 branch and executed the full-data experiment. Added a reproducible aggregate-only audit helper and focused tests. No production retrieval, matcher, calibration, or submission behavior changes.

Predictors are the same Source-1-only structural/frequency family used in D001a: raw/normalized lengths, token counts, digit/numeric-token counts, non-ASCII/punctuation/whitespace counts, normalization-retention ratios, normalized name/address/name+address frequencies, and log-frequency transforms. Country is deliberately excluded. Entity ID is used only for deterministic fold assignment.

## Protocol

Inputs, complete and unsampled:

- `train_source1.tsv`: **2,206,821** anchors, 210,069,713 bytes, SHA-256 `591af0e1dfeb65cab71ea6ee8cb69df00f92d6ba6fa79e05746c938775d14973`
- `train_ground_truth.tsv`: 127,015,583 bytes, SHA-256 `70bc1d8a16c667e0155c2105d0ab2ebe41d7e7a85d8a529e3ca81c6c3a5af037`
- no Source-2/Source-3 text is needed; target-source presence comes only from supplied truth-ID prefixes
- no confirmation or frozen holdout was consumed
- no external entity data

Split: exact repository `fold517` rule, first 8 hex digits of `sha256('fold517:'+entity_id)` modulo 100: fit 60%, early 15%, calibrate 15%, holdout 10%.

Observed fold counts:

| Fold | Anchors |
|---|---:|
| fit | 1,323,457 |
| early | 330,681 |
| calibrate | 331,219 |
| holdout | 221,464 |

Five binary targets: S2-present, S3-present, both-source, S2-only, S3-only.

Primary model: CatBoost, fixed 100 trees, depth 7, learning rate 0.08, L2 5, seed 517. Fixed-tree evaluation avoids turning early stopping into another hidden selection knob. The runtime had CatBoost 1.2.8, while the repository's documented pin is 1.2.10.

Normalization uses the same NFD combining-mark-removal fallback documented in D001a because this runtime did not have DuckDB's `strip_accents` available. Exact normalized name+address pairs are unique in this inventory; normalized-name collision anchor rate is 39.2825% and address collision anchor rate is 5.3090%.

Reproduction:

```bash
PYTHONPATH=src python -m ber.source_presence_audit \
  --source1 /path/to/train_source1.tsv \
  --truth /path/to/train_ground_truth.tsv \
  --out /tmp/d012.json \
  --seed 517 --trees 100

PYTHONPATH=src python -m unittest tests/test_source_presence_audit.py -v
```

Focused tests passed **3/3**. Primary full-data run took about **120.8 s** end-to-end; the S2-only seed replication took another **21.2 s**. Peak process RSS was about 2.3 GiB in this runtime.

## Baseline

This task has no existing source-presence classifier, so the correct probability baseline is a constant fit-set prevalence. D001a is the closest prior result: Source-1-only singleton prediction was chance-level on holdout (AUROC **0.500142**). D006a showed source composition is common but not country-specific: 85.2404% of non-singletons use both S2 and S3, with nearly identical US/India cardinality structure.

Current selected end-to-end INT002 context is macro F0.5 **0.940478** on its 5,000-anchor confirmation, India **0.913639**, US **0.958045**, singleton FPR **5.8182%**, and retrieval oracle **0.974176**. Those values are context only; D012 does not re-evaluate or tune that consumed confirmation window.

## Results

Population prevalences are S2-present 86.9611%, S3-present 87.9340%, both-source 80.4799%, S2-only 6.4812%, and S3-only 7.4541%.

| Target | Holdout prevalence | AUROC | Approx. 95% AUROC interval | AUPRC − prevalence | Brier − constant prior | US AUROC | India AUROC |
|---|---:|---:|---:|---:|---:|---:|---:|
| S2-present | 0.86910 | **0.50058** | [0.49702, 0.50415] | +0.00023 | +0.0000032 | 0.50306 | 0.49654 |
| S3-present | 0.87873 | **0.50139** | [0.49771, 0.50507] | +0.00018 | +0.0000053 | 0.49985 | 0.50343 |
| Both-source | 0.80422 | **0.50127** | [0.49824, 0.50430] | +0.00041 | +0.0000082 | 0.50237 | 0.49963 |
| S2-only | 0.06488 | **0.50424** | [0.49934, 0.50913] | +0.00109 | +0.0000009 | 0.50404 | 0.50397 |
| S3-only | 0.07451 | **0.50183** | [0.49724, 0.50641] | +0.00043 | +0.0000009 | 0.50135 | 0.50220 |

Positive Brier deltas are bad: every learned model is slightly worse than simply predicting the fit-set prevalence.

Fit AUROCs ranged from about 0.514 to 0.523, then collapsed to ~0.5 on early/calibration/holdout. This is the same weak-memorization pattern seen in D001a.

### Red-team of the only tempting result

S2-only had the largest holdout AUROC, 0.50424, but its approximate interval crosses 0.5. A second fixed-100-tree run with seed 2026 falls to:

- AUROC **0.502504**
- AUPRC **0.065288**
- prediction correlation with seed 517: **0.6718**

There is no useful high-purity tail. On seed 517, the top 100 / 1,000 / 10,000 / 50,000 holdout predictions contain 6.0% / 6.5% / 7.0% / 6.722% S2-only anchors versus 6.488% prevalence. Seed 2026 is even less stable: 4.0% / 6.1% / 6.49% / 6.656%.

## Error analysis

1. **No transferable anchor-only source signal.** All five holdout AUROCs are statistically and practically indistinguishable from chance.
2. **US and India do not rescue the hypothesis.** Slice AUROCs remain around 0.5, matching D006a's finding that source/cardinality prevalence barely differs by country.
3. **Fit-only lift is memorization, not mechanism.** Training AUROCs rise into the low 0.52s while every unseen split collapses.
4. **Probability calibration is not improved.** Every learned Brier score is slightly worse than the constant fit-prior predictor.
5. **The S2-only blip is fragile.** It shrinks under a second seed and does not create a useful precision tail.

## Interpretation

Source-1 business-name/address shape and Source-1 corpus frequency do not tell us whether the target inventory happens to contain S2, S3, both, or source-exclusive matches. This independently reinforces D001a's null Source-1-only singleton result.

The promising part of D004/D008 remains **candidate evidence**, not an anchor prior: source-specific candidate probabilities, top-score/margin, credible-candidate counts, retriever provenance, address/number conflicts, and S2/S3 agreement should be tested out of fold. Population prevalence should not be converted into a hard source-presence rule.

## Risks / red-team checks

- **ID leakage:** PASS. IDs only assign `fold517`; they never enter features.
- **Label leakage into features:** PASS. Source-presence labels come from truth IDs; features use Source-1 text/frequencies only.
- **Sampling mismatch:** PASS. Complete S1 + truth were used.
- **Confirmation tuning:** PASS. No confirmation/frozen window was read.
- **Country leakage:** PASS. Country is slice metadata only, not a predictor.
- **Seed fragility:** CHECKED for the best-looking S2-only target; the tiny lift shrank.
- **Normalizer parity:** minor limitation shared with D001a. NFD combining-mark removal replaces DuckDB `strip_accents`.
- **CatBoost patch version:** runtime 1.2.8 vs documented repository pin 1.2.10. The null effect is far too small and unstable to justify promotion regardless.

No raw challenge rows, row-level predictions, model binaries, or external identity data are committed.

## Recommendation

**REJECT** Source-1-only source-presence priors.

Do not add these features as D004/D008 priors and do not spend more tuning budget on anchor-only source-presence models. Future source-aware decision work should require reusable candidate/pair-score evidence and report official macro F0.5, singleton FPR, US/India slices, candidate recall, and threshold/calibration details on identical anchors.

## Follow-up

Use D012 as a negative control when D004/D008 are eventually executed: any source-aware gain should come from candidate-level evidence, not country or Source-1 structural priors.
