# R030 — adaptive address-word probe budget for India retrieval

## Hypothesis

F007a found a large country asymmetry under its Source-1 DF proxy: the current four-rarest address-word query budget dropped 7.5150% of eligible India address keys but only 0.0123% in the US. The question here is whether a bounded wider or adaptive probe budget can recover most of that discarded lexical evidence without a proportionate increase in estimated posting/query work.

This is deliberately a **Source-1 proxy audit**, not a retrieval-score experiment. Production blocker eligibility and ordering use pooled S2+S3 target posting frequencies. The large target files are above this chat runtime's Drive raw-download ceiling, so no target recall, oracle, candidate-count, or macro-F0.5 claim is made.

## Change

Analysis-only helper `tools/experiments/r030_adaptive_address_probes.py` compares:

- fixed 4 rarest eligible address words (F007a parity baseline);
- fixed 6;
- fixed 8;
- adaptive 4→8 with four baseline probes plus additional rarest probes only while cumulative extra Source-1 proxy DF stays <=200.

Eligibility stays DF<=1000. Tokenization, accent folding, Unicode letter/number semantics, and the address stop list match F007a's committed proxy logic. No production blocker default changes.

## Protocol

Complete supplied Source-1 populations, no sampling:

- train: 2,206,821 anchors; SHA-256 `591af0e1dfeb65cab71ea6ee8cb69df00f92d6ba6fa79e05746c938775d14973`;
- test: 1,732,544 anchors; SHA-256 `3d4a32c54c2ca9c53fd7c2be105bf26f708f94c4d2f88eb370972a195665c2f5`;
- country/split-local Source-1 address-word DF;
- eligible token cutoff DF<=1000;
- Python 3.13.5 / pandas 2.2.3 chunked execution;
- two complete passes over each file;
- measured cell execution wall times sum to 306.94 s; inter-call idle time excluded;
- 4/4 focused policy/normalization tests pass in 0.003 s.

No labels, confirmation/frozen holdout, leaderboard feedback, record IDs as evidence, France pseudo-labels, or external identity data were used.

### Integrity / parity

The fixed-4 train baseline reproduces F007a exactly on its headline quantities:

| Slice | Address vocab | Eligible keys | Dropped at k=4 |
|---|---:|---:|---:|
| US train | 104,930 | 1,672,031 | 205 |
| India train | 309,602 | 2,274,335 | 170,917 |

That exact parity is important because F007aR correctly warned that the result is a proxy for production target-side frequency, not production blocker truncation.

## Results

### Eligible-key retention and proxy posting cost

| Slice | Policy | Dropped eligible keys | Drop rate | Fixed-4 drops recovered | Proxy posting-mass change vs k=4 |
|---|---|---:|---:|---:|---:|
| India train | fixed4 | 170,917 | 7.5150% | — | — |
| India train | fixed6 | 21,918 | 0.9637% | 87.18% | +16.30% |
| India train | fixed8 | 2,067 | 0.0909% | 98.79% | +18.90% |
| India train | adaptive200 | 138,570 | 6.0928% | 18.93% | +0.755% |
| India test | fixed4 | 169,050 | 7.9031% | — | — |
| India test | fixed6 | 22,295 | 1.0423% | 86.81% | +17.28% |
| India test | fixed8 | 2,082 | 0.0973% | 98.77% | +20.13% |
| India test | adaptive200 | 137,331 | 6.4203% | 18.76% | +0.792% |
| US test | fixed4 | 249 | 0.0241% | — | — |
| US test | fixed6 | 4 | 0.00039% | 98.39% | +0.0527% |
| France test | fixed4 | 2,620 | 0.7491% | — | — |
| France test | fixed6 | 341 | 0.0975% | 86.98% | +1.407% |
| France test | adaptive200 | 1,887 | 0.5395% | 27.98% | +0.110% |

Across the complete test Source-1 population, fixed6 recovers 149,279 / 171,919 = **86.83%** of the keys discarded by fixed4 at **+9.43%** aggregate proxy posting mass. Fixed8 recovers **98.77%** at **+10.98%**. Adaptive200 recovers only **18.89%**, but costs just **+0.436%** proxy posting mass.

### Why India is different

Eligible address-word counts explain the asymmetry without invoking labels:

- India train: p90=5, p95=5, p99=7 eligible words.
- India test: p90=5, p95=6, p99=7.
- US train/test: p99=3.
- France test: p99=4.

A hard four-probe budget is therefore almost never binding in the US, sometimes binding in France, and routinely binding in India. The India train→test fixed4 drop rate is stable in direction and magnitude: 7.5150% → 7.9031%.

### Cost efficiency

On India test, adaptive200 recovers 31,719 discarded keys using 3,037,337 additional proxy postings, about **10,443 recovered keys per million extra proxy postings**. Fixed6 recovers 146,755 using 66,277,316 additional proxy postings, about **2,214 per million**. The adaptive policy is ~4.7x more proxy-efficient, but it leaves most of the fixed4 truncation intact.

This is exactly the tradeoff the eventual target-side experiment needs to resolve: lexical coverage versus actual candidate pressure and marginal positive recovery.

## Error analysis

1. **Fixed4 under-probes India-rich addresses.** The p90/p95 eligible-token counts reach or exceed five, so truncation is structural rather than a handful of outliers.
2. **US has essentially no headroom from wider address-word probing.** Even k=4 already retains >99.97% of eligible test proxy keys.
3. **France is intermediate.** Fixed6 removes most proxy truncation, but France has no labels, so this is only a robustness/candidate-pressure diagnostic.
4. **Adaptive200 is too conservative for coverage.** Its strict cumulative extra-DF budget preserves excellent cost efficiency but recovers only ~19% of India fixed4 drops.
5. **Fixed8 has diminishing coverage returns after fixed6.** On India test, fixed6 already recovers 146,755 dropped keys; fixed8 adds another 20,213 while increasing proxy posting mass by another 10.95M. Whether those late probes recover true target links remains unknown.

## Risks / red-team checks

- **Proxy mismatch:** Source-1 country/split-local DF is not the production S2+S3 target posting frequency. F007aR's warning remains fully applicable.
- **No F0.5 or oracle evidence:** no S2/S3 target rows were substituted or sampled.
- **No label leakage:** ground truth was not used.
- **No confirmation leakage:** no confirmation/frozen window was read.
- **No France labels:** France metrics are unlabeled structural diagnostics only.
- **No ID evidence:** entity IDs are not used by the analysis.
- **No production change:** current blocker behavior remains untouched.

## Recommendation

**FOLLOW-UP / PROMOTE TO TARGET-SIDE GATE.**

The first complete-target benchmark should compare the current fixed4 address-word policy against **fixed6** and **adaptive200** at the same final candidate cap and on the same development/calibration anchors. Fixed6 is the high-coverage candidate; adaptive200 is the low-cost candidate. Report pair/entity/all-match recall, blocking oracle macro F0.5, actual candidate quantiles, US/India and source slices, runtime/memory, and marginal recovered positives per added candidate.

Do **not** spend the first full-target run on fixed8. Test it only if fixed6 proves that the extra India address probes recover true links at acceptable candidate cost.

## Reproduction

```bash
python tools/experiments/r030_adaptive_address_probes.py \
  --train-source1 /path/to/train_source1.tsv \
  --test-source1 /path/to/test_source1.tsv \
  --out reports/swarm/R030-adaptive-address-probes.json

python -m unittest tests/test_r030_adaptive_address_probes.py -v
```
