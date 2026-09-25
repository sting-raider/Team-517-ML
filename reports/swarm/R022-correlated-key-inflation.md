# R022 — correlated-key score inflation in blocker v2

## Hypothesis

Blocker v2 sums retrieval contributions from many deterministic keys derived from the same underlying name/address evidence. If one address fact can emit enough exact-address, address-word, adjacent-word, and number-composite hits, that correlated evidence may dominate candidate rank and consume a bounded candidate budget even against candidates supported by several independently rare name tokens.

## Change

No production retrieval behavior was changed. This branch adds a deterministic standard-library audit helper and focused tests that mirror the scoring rule in `src/ber/blocking.py`:

`bonus(kind) + ln(10000001 / freq)`, summed over every shared key.

The helper also includes an explicitly illustrative “family max” comparator that takes only the strongest contribution per broad evidence family. It is a diagnostic, not a recommended production scorer.

## Protocol

- Base: main at `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`.
- Tier: 0/1 static + deterministic synthetic audit.
- Current full-data calibration context, not re-evaluated here: cap-640 pair recall **0.945863**, all-matches-retrieved rate **0.841189**, blocking-oracle macro F0.5 **0.981178** on 4,389 calibration anchors.
- Synthetic address cases contain 1–4 eligible address words, an address number, and the `h:` name-prefix+number key. Every address-derived key is assigned `freq=1000`, the *weakest* IDF still admitted by blocker v2.
- The competing name-only candidate receives four `w:` keys at `freq=1`, the *strongest possible* IDF under blocker v2’s four-name-token query limit.
- Exact score arithmetic is evaluated with Python stdlib only.
- Command:
  `python tools/experiments/r022_correlated_key_inflation.py --out /tmp/r022.json`
- Tests:
  `python -m unittest -v tests/test_r022_correlated_key_inflation.py`
- Runtime in this chat container: below one second; 5/5 focused tests passed.
- No confirmation/frozen holdout was consumed.

Full train Source 2 (489,301,488 bytes) and Source 3 (503,705,637 bytes) are visible in the shared Drive but the connector rejects raw downloads above 268,435,456 bytes. No sample was substituted.

## Results

| Eligible address words | Scoring hits from same address evidence | Current summed score | Inflation vs exact-address-only | Family-max diagnostic | Four maximally rare name words |
|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 100.841 | 2.049× | 83.631 | 64.472 |
| 2 | 7 | 152.472 | 3.098× | 83.631 | 64.472 |
| 3 | 10 | 204.103 | 4.148× | 83.631 | 64.472 |
| 4 | 13 | 255.734 | 5.197× | 83.631 | 64.472 |

The key result is deliberately conservative: even with every address-derived key at the blocker’s maximum eligible frequency of 1000, the **one-word address stack scores 100.841**, exceeding **64.472** from four maximally rare shared name words. At four eligible address words, the same underlying address evidence is counted across 13 scoring hits and reaches **255.734**, 5.197× the exact-address contribution alone.

This confirms the mechanism: blocker-v2 rank is sensitive not only to rarity and field agreement but also to how many correlated keys a field happens to emit.

No official macro F0.5, pair recall, entity recall, or oracle delta is claimed from this synthetic audit.

## Error analysis

1. **Same-building / exact-address hard negatives.** A different business at the same normalized address can accumulate exact-address plus derived address-word/bigram/number evidence even when name evidence points elsewhere. This is the highest-risk semantic case for score multiplication.
2. **Address-length dependence.** More eligible address words mechanically create more `u:`, `v:`, and `d:` opportunities. Under the current sum, otherwise similar evidence can receive a larger score simply because the address yields more derived keys.
3. **Repeated number evidence.** `h:` and multiple `d:` keys can all reuse the same address number while each receiving the generic +8 bonus and an IDF term.
4. **Bounded-cap relevance.** The committed calibration study has p50 candidate count 597 and p90/p99 at 640 for cap 640. Ranking changes therefore can plausibly affect which candidates survive the cap; this audit does not measure how often the correlated-key pattern crosses the cutoff.
5. **Potential legitimate benefit.** Exact shared address plus several compatible components may genuinely be strong positive evidence. The audit proves overcounting potential, not that all such rank boosts are wrong.

## Interpretation

The hypothesis is **confirmed as a scoring-structure failure mode**: blocker v2 can multiply one underlying address fact into several additive retrieval contributions, and the multiplication is large enough to outrank the strongest four-token name-only evidence in a conservative synthetic case.

That is useful because it identifies a distinct retrieval lever not covered by simply widening the cap or adding another retrieval channel. However, changing production scoring now would be premature. The same correlated keys may currently rescue real positives, and without the full S2/S3 inventory this runtime cannot measure the net effect on pair recall, entity recall, all-matches-retrieved rate, blocking oracle, or candidate count.

## Risks

- Synthetic construction cannot estimate prevalence of same-address hard negatives or cutoff crossings.
- The illustrative family-max comparator is only one possible decorrelation rule and is not tuned or promoted.
- Full S2/S3 raw files exceed this connector’s 256 MiB download ceiling; no partial sample was used as a substitute.
- A production reranker could lower recall if correlated address evidence is genuinely useful for noisy positives.
- Any full-data follow-up must use the exact same calibration anchors and candidate budget, and must not touch confirmation/frozen holdout.

## Recommendation

**FOLLOW-UP.**

Do not change blocker v2 on this evidence alone. Run a paired full-data calibration experiment in a runtime with complete S2/S3 access, reranking the *same raw candidate union* with at least:

1. current summed score,
2. max-per-key-kind score,
3. a broad-family-capped score similar to this diagnostic.

Report official retrieval metrics, country/source slices, candidate-count quantiles, and the number of true links entering/leaving the cap. A useful variant should improve oracle/pair recall or preserve them while shrinking the candidate budget; otherwise reject it.

## Follow-up tasks

- Measure how often exact-address candidates near the cap are distinct-name hard negatives versus true positives, especially India.
- On the same candidate union, compute rank changes and recovered/lost positives under decorrelated scoring before rebuilding any index.
- If a variant is promising, add candidate-rank/provenance features so the matcher can still exploit raw key multiplicity without letting it control blocking rank unboundedly.
