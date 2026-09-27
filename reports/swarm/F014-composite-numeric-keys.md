# F014 — Composite numeric-text retrieval-key feasibility

**Issue:** #237  
**Pod:** R/F  
**Branch:** `agent/r/F014-composite-numeric-keys`  
**Recommendation:** **REJECT** unconditional first-number + full-name-token retrieval; **FOLLOW-UP** only as a target-side conditional rescue probe

## Hypothesis

F003a showed that address-number-only evidence is often collision-prone in India and unseen France. The bounded F014 question is whether combining the **first normalized address number** with each distinct normalized business-name token (length >= 3) creates materially more selective Source-1 retrieval keys than the current production-style first-number + address-word `d:` family, strongly enough to justify adding another generic numeric retrieval family.

## Change

No production retrieval, matcher, threshold, or submission behavior changed.

The branch contains an analysis-only helper that computes country-local Source-1 document frequency for three comparable families:

- `number`: first normalized address digit run;
- `number_name`: first address number + each distinct normalized name token with length >= 3;
- `number_address`: first address number + each distinct production-style address word, mirroring the existing `d:` family.

Latest-main already has `d:`, plus `h:` / `z:` name-prefix+number composites. F014 therefore tests whether the proposed full-name-token composite has a clear selectivity advantage before spending a scarce full-target S2/S3 benchmark on it.

## Protocol

The complete supplied Source-1 populations were fetched from the shared Drive and processed with **no sampling**:

- `train_source1.tsv`: 210,069,713 bytes; 2,206,821 anchors
  - US 1,323,633
  - India 883,188
- `test_source1.tsv`: 175,022,086 bytes; 1,732,544 anchors
  - US 663,106
  - India 809,986
  - France 259,452

Normalization and token semantics reproduce the branch helper:

1. NFD normalize and strip combining marks;
2. lowercase;
3. replace non-alphanumeric characters with spaces and collapse whitespace;
4. use the first ASCII digit run from normalized address;
5. deduplicate emitted name/address tokens per record;
6. address tokens use the same stopword set as the production blocker helper.

For each split/country/family, the census records best (minimum) Source-1 DF per anchor at cutoffs {1,2,5,10,50,100,1000}, best-DF quantiles, emitted-key burden, and rescue over the first-number-only baseline.

The normal container/private-Python surfaces failed at session startup, but the remaining Python execution surface was healthy. The census was therefore streamed country-at-a-time with pandas chunks to bound memory. The authored synthetic normalization/dedup and four-row rescue expectations were independently executed and **PASS**. Fresh `number_address` DF<=1000 rates reproduce the prior complete-population X008 production-style `d:` proxy rates to four decimals, providing an external parity check.

Summed country-pass compute time: **342.76 s**. Peak RSS: **1,284,292 KiB** (~1.23 GiB).

No ground-truth labels, S2/S3 records, candidate probabilities, confirmation/frozen holdout, leaderboard feedback, external business data, France pseudo-labels, or record IDs as predictive evidence were used.

## Results

### DF <= 1000: the new family adds essentially no Source-1 selectivity

All rows below use the fresh **same first-address-number semantics**, unlike F003a's older any-address-number comparator.

| Population | First number only | Number + name token | Number + address word (`d:` proxy) | Name minus address |
|---|---:|---:|---:|---:|
| train US | 78.4069% | 99.9998% | 99.9992% | +0.0007 pp |
| train India | 26.4263% | 91.1273% | 91.2494% | **-0.1222 pp** |
| test US | 90.8075% | 99.9998% | 99.9991% | +0.0008 pp |
| test India | 27.1706% | 91.1265% | 91.2419% | **-0.1154 pp** |
| test France | 23.7161% | 99.5799% | 99.5722% | +0.0077 pp |

At the production-style DF<=1000 screening level, the proposed name-token composite is effectively tied with the already-existing address composite. Its largest positive difference is only **+0.0077 percentage points in unlabeled France**, while India is slightly worse on both train and test.

Fresh rescue counts over first-number-only at DF<=1000 show the same result:

- train India: name **571,576** anchors vs address **572,510**;
- test India: name **518,175** vs address **518,969**;
- test France: name **196,830** vs address **196,810**.

Twenty additional Source-1 France anchors are not evidence of candidate recall, much less accuracy.

### At stricter selectivity, the existing address composite is materially better in India and France

| Population | Number + name token, DF<=10 | Number + address word, DF<=10 | Name minus address |
|---|---:|---:|---:|
| train US | 98.8770% | 99.3638% | -0.4868 pp |
| train India | 66.8928% | 83.8383% | **-16.9455 pp** |
| test US | 99.7969% | 99.8769% | -0.0801 pp |
| test India | 67.6178% | 84.2613% | **-16.6435 pp** |
| test France | 78.3363% | 95.0642% | **-16.7279 pp** |

Best-key DF quantiles make the same point. For test India, number+name has median / 99th-percentile DF **2 / 262**, while number+address has **1 / 87**. For France the corresponding values are **2 / 219** versus **1 / 42**.

So the proposed family is not merely failing to dominate at the loose cutoff; it is substantially less selective in the exact India/France regimes that motivated the experiment.

### Probe burden is lower for name tokens in India/France, but that is not enough

Mean emitted keys per anchor:

| Population | Number + name token | Number + address word |
|---|---:|---:|
| train US | 3.145 | 2.661 |
| train India | 3.273 | 7.026 |
| test US | 3.144 | 2.662 |
| test India | 3.271 | 7.023 |
| test France | 2.808 | 5.780 |

The name-token family is cheaper in India/France, but Source-1 probe count is not the competition objective. The full target inventory can have very different posting frequencies, and a cheaper channel is useful only if it recovers true links that existing `d:/h:/z:` and character retrieval miss.

## Error analysis / interpretation

1. **Numeric+lexical composition is genuinely useful.** First-number-only evidence has poor DF<=1000 coverage in India and France, while either composite family makes most number-bearing anchors selective.
2. **The obvious useful composite already exists.** Production-style number+address-word keys are at least as broadly eligible at DF<=1000 and much more selective at DF<=10 in India and France.
3. **The new full-name-token family lacks an unconditional mechanism.** Its only credible remaining value is corruption complementarity: a true pair where address-word or six-character name-prefix evidence is damaged but another business-name token and the number survive.
4. **That remaining question requires target-side positives.** Source-1 collision statistics cannot establish pair recall, candidate efficiency, oracle F0.5, or matcher gain.
5. **France remains unlabeled.** Its Source-1 statistics are robustness diagnostics only.

## Risks / red-team checks

- Production posting frequency is computed over the pooled S2/S3 target inventory, while this experiment is a Source-1 collision/selectivity proxy.
- The current chat reconfirmed that each raw S2/S3 file exceeds the Drive connector's 256 MiB raw-transfer ceiling, so no full-target retrieval metric is claimed here.
- F003a's previously reported number-only rates used the best among any distinct address numbers. This fresh F014 census uses the **first** address number consistently for all three families. Those two baselines must not be mixed.
- The branch helper itself was not invoked through the unavailable container backend; its exact semantics were reproduced in the working Python surface, and the authored synthetic expectations plus prior X008 `d:` aggregate parity were checked.
- No ID/label leakage, threshold retuning, candidate-cap change, stale candidate cache, confirmation reuse, or sampling difference exists because this experiment never constructs candidates or trains/scores a model.

## Recommendation

**REJECT** adding or prioritizing an unconditional first-number + full-name-token retrieval family on Source-1 selectivity grounds.

The evidence-backed follow-up is narrower: on a runtime with the complete target inventory, test the proposed family **only as a conditional rescue channel for anchors/positives not already recovered by existing `d:/h:/z:` and INT003 character retrieval**, at a fixed final cap. Required metrics are marginal pair/entity/all-matches recall, blocking-oracle macro F0.5, US/India and S2/S3 slices, candidate-count quantiles, recovered positives per added candidate, and runtime/memory.

A generic extra key family would otherwise mostly add correlated retrieval evidence, because humanity apparently did manage to invent multiple ways to rediscover the same address number.

## Reproduction

Branch helper:

```bash
python tools/experiments/f014_composite_numeric_keys.py \
  --source1 /path/train_source1.tsv --split train --countries US India \
  --out /tmp/f014-train.json

python tools/experiments/f014_composite_numeric_keys.py \
  --source1 /path/test_source1.tsv --split test --countries US India France \
  --out /tmp/f014-test.json

python -m unittest tests.test_f014_composite_numeric_keys -v
```
