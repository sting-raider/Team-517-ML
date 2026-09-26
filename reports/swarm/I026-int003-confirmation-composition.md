# I026 — INT003 confirmation composition and India-singleton audit

## Hypothesis

INT003's already-consumed confirmation window at sample517 hash positions 45,001–50,000 should be compositionally close to the complete labeled Source-1 population. In particular, the reported India singleton false-positive change (6/114 for v2 to 8/114 for v3 on this window) should not be interpreted as a model effect if the window itself contains an unusual India-singleton prevalence or an obvious Source-1 text-shape shift.

## Change

No production retrieval, matcher, feature, threshold, or export code changed. This is an evaluation-integrity audit.

A dependency-light script, `experiments/i026_int003_confirmation_composition.py`, reconstructs the deterministic sample517 order from the complete supplied Source-1 population while keeping only the 50,000 smallest MD5 ordering keys in memory. It joins complete ground-truth cardinality by Source-1 ID, summarizes the full population, then characterizes only the already-consumed INT003 window.

## Protocol

- Complete `train_source1.tsv`: **2,206,821** anchors, SHA-256 `591af0e1dfeb65cab71ea6ee8cb69df00f92d6ba6fa79e05746c938775d14973`.
- Complete `train_ground_truth.tsv`: **2,206,821** rows, SHA-256 `70bc1d8a16c667e0155c2105d0ab2ebe41d7e7a85d8a529e3ca81c6c3a5af037`.
- Ordering: ascending `md5('sample517:' || entity_id)`.
- Audited window: one-based positions **45,001–50,000**, i.e. zero-based `[45000,50000)`.
- No new/future confirmation window was inspected.
- IDs are used only for deterministic sampling. No S2/S3 text, candidates, predictions, model probabilities, threshold changes, France pseudo-labels, or leaderboard feedback enter the audit.
- Command:

```bash
python experiments/i026_int003_confirmation_composition.py \
  --source1 /path/to/train_source1.tsv \
  --truth /path/to/train_ground_truth.tsv \
  --out reports/swarm/I026-int003-confirmation-composition.json
```

Focused helper tests: **3/3 PASS**. Full run wall time **24.72 s**, peak RSS **317.24 MiB** in the ChatGPT container.

## Results

### Exact parity with committed INT003 aggregates

The reconstructed window exactly matches all committed count facts from `reports/int003_depth10_confirmation.json`:

| Count | Committed | Reconstructed |
|---|---:|---:|
| Anchors | 5,000 | 5,000 |
| India | 2,022 | 2,022 |
| US | 2,978 | 2,978 |
| Singletons | 262 | 262 |
| India singletons | 114 | 114 |
| US singletons | 148 | 148 |

This independently verifies that the audit reconstructed the same INT003 confirmation population rather than a neighboring hash slice.

### Population composition

| Metric | Full population | INT003 window | Difference |
|---|---:|---:|---:|
| India share | 40.0208% | 40.4400% | +0.4192 pp, z=0.605 |
| Singleton rate | 5.5848% | 5.2400% | -0.3448 pp, z=-1.062 |
| India singleton rate | 5.5878% | 5.6380% | +0.0502 pp, z=0.098 |
| US singleton rate | 5.5828% | 4.9698% | -0.6130 pp, z=-1.457 |
| Mean truth cardinality | 3.4613 | 3.5148 | +0.0535, SMD=0.0314 |
| 5+ truth matches | 26.0215% | 27.6000% | **+1.5785 pp, z=2.544** |

The largest audited departure is the 5+ cardinality bucket. That is a real composition caveat worth recording, but the corresponding shift in mean truth cardinality is small in standardized terms (SMD 0.0314). Basic Source-1 text-shape means are also close: the largest absolute SMD across name/address length and token count is **0.0246**.

### India-singleton slice

The India singleton prevalence is essentially identical to the population (+0.0502 pp, z=0.098). The 114 singleton anchors also show no conspicuous basic Source-1 text-shape shift relative to all 49,351 labeled India singletons:

| India singleton observable | Window vs population SMD |
|---|---:|
| Name length | +0.0140 |
| Name token count | -0.0517 |
| Address length | -0.0643 |
| Address token count | -0.0648 |

Name/address missing-rate differences are both 0 pp.

## Error analysis

1. **High-cardinality tilt:** 5+ match anchors are overrepresented by 1.58 pp (z≈2.54). The paired v3-v2 comparison remains valid because both models are scored on the same anchors, but the absolute 0.950198 headline may reflect a slightly different cardinality mixture than the complete labeled population. This audit cannot determine whether 5+ rows are intrinsically easier or harder for the model without reusing prediction-level confirmation outputs for a new analysis.
2. **India singleton regression is not a prevalence artifact:** India singleton prevalence is nearly population-exact, and the basic Source-1 text shape of those 114 rows is ordinary. The observed 6→8 false-positive increase therefore is not explained by an obvious singleton-composition anomaly on the measured observables.
3. **US singleton underrepresentation:** US singleton prevalence is 0.61 pp lower than population, but the descriptive z is only -1.46.
4. **Scope boundary:** candidate ambiguity, target-side commonness, retrieval provenance, and hard-negative density are not observable from Source-1 + truth alone. Those are more plausible mechanisms for the India singleton errors and require development/calibration candidate evidence, not further tuning on this consumed confirmation block.

## Interpretation

The main INT003 paired result remains credible on the audited axes. The window is not grossly country- or singleton-skewed, and the exact count parity strongly supports reconstruction correctness. The modest 5+ cardinality excess should qualify absolute-score interpretation, but it does not explain away a paired +0.007914 v3-v2 gain measured on identical anchors.

For the India singleton tradeoff, this audit narrows the mechanism: the regression is more likely to come from candidate/matcher behavior than from an unusually singleton-heavy or structurally odd India sample. Further work should analyze candidate-score gaps, retrieval channels, and false-positive evidence on development/calibration anchors only.

## Risks

- This is a Source-1 + ground-truth composition audit, not an end-to-end re-evaluation.
- It cannot assess target-side ambiguity or whether the 5+ cardinality tilt makes matching easier or harder.
- The India singleton window contains only 114 rows, so two additional errors produce a visibly noisy rate change.
- The confirmation window is consumed. It must remain excluded from future model, threshold, and feature selection.

## Recommendation

**PROMOTE** the INT003 confirmation window as compositionally acceptable for the paired v2-v3 comparison, with the documented 5+ cardinality caveat. Do not retune on it.

## Follow-up

Use development/calibration candidate artifacts to characterize India singleton false positives by retrieval provenance, top-score/margin, target frequency, and character-vs-lexical evidence. That is the evidence-bearing next step; another Source-1-only singleton prior is not, given the already-negative D001a/D012 results.
