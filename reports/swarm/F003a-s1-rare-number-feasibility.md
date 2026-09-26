# F003a — Full Source-1 rare-number retrieval-key feasibility

## Hypothesis

Distinctive numeric tokens in Source-1 business names and addresses are common enough and sufficiently selective to justify dedicated rare-number retrieval keys and rare-number agreement/conflict matcher features.

## Change

No production retrieval or matcher behavior changed. This recovery replaces the prior BLOCKED checkpoint with a deterministic full-Source-1 census helper, focused unit tests, and measured train/test aggregates.

The census extracts maximal ASCII digit runs using [0-9]+ from raw name/address fields. This matches the numeric view used by the current blocker/matcher: repository normalization preserves digits while converting punctuation separators to spaces, and blocker/features use the same digit-run semantics. Document frequency (DF) is counted once per record, separately by split, country, and field.

## Protocol

- Task / issue: F003a / #23
- Recovery branch: agent/r/F003a-recovery-rare-number
- Complete train_source1.tsv: 210,069,713 bytes; SHA256 591af0e1dfeb65cab71ea6ee8cb69df00f92d6ba6fa79e05746c938775d14973
- Complete test_source1.tsv: 175,022,086 bytes; SHA256 3d4a32c54c2ca9c53fd7c2be105bf26f708f94c4d2f88eb370972a195665c2f5
- No sampling. Full train/test Source-1 populations only.
- Country-local, field-local distinct-per-record DF.
- Practical DF cutoffs: 1, 2, 5, 10, 50, 100, 1000.
- Metrics: numeric presence, distinct numeric-token types, record-weighted minimum/best DF, token-type DF, per-record numeric multiplicity, digit-run lengths, repeated numeric tokens, leading zeros, year-like runs, and long-run hazards.
- Ground-truth labels, S2/S3 records, confirmation/frozen holdouts, leaderboard feedback, record IDs as predictive evidence, and external identity data were not used.

Reproduction:

    python tools/source1_rare_number_census.py --input /path/to/train_source1.tsv --split train --out artifacts/f003a_train_numbers.json
    python tools/source1_rare_number_census.py --input /path/to/test_source1.tsv --split test --out artifacts/f003a_test_numbers.json
    python -m unittest tests/test_source1_rare_number_census.py -v

The empirical census used two complete passes over each file. Measured core analysis time was 41.382 s for train (22.568 s pass 1 + 18.813 s pass 2) and 33.990 s for test (18.084 s + 15.906 s) in the initial full run. A later full test-file replay through the committed helper completed in 28.099 s and matched every non-runtime aggregate exactly. The train helper replay hit this chat container wrapper's single-call wall limit; the original full train two-pass computation completed and its population counts match the repository census.

Focused synthetic tests: 2/2 PASS.

## Results

### Population and broad numeric coverage

| Split | Country | S1 records | Any numeric | Name numeric | Address numeric |
|---|---|---:|---:|---:|---:|
| train | US | 1,323,633 | 99.9999% | 2.6060% | 99.9999% |
| train | India | 883,188 | 91.2782% | 0.1235% | 91.2775% |
| test | US | 663,106 | 99.9998% | 2.5851% | 99.9998% |
| test | India | 809,986 | 91.2664% | 0.1312% | 91.2655% |
| test | France | 259,452 | 99.5822% | 0.7716% | 99.5803% |

Address numbers have enormous coverage; name numbers are too sparse to serve as a primary channel.

### Record-weighted address-number selectivity

A record's best DF is the lowest country-local address DF among its distinct numeric runs. This is the operational statistic for a number-only retrieval probe: many rare token types are irrelevant if most records only contain common numbers.

| Split | Country | Distinct address-number types | Median best DF | Median best DF / country rows | DF<=10 coverage | DF<=100 coverage | DF<=1000 coverage |
|---|---|---:|---:|---:|---:|---:|---:|
| train | US | 42,433 | 236 | 0.01783% | 6.0997% | 32.7501% | 75.1337% |
| train | India | 10,931 | 2,377 | 0.26914% | 2.1716% | 8.3090% | 30.8302% |
| test | US | 33,871 | 120 | 0.01810% | 10.4917% | 46.6854% | 85.4904% |
| test | India | 10,437 | 2,160 | 0.26667% | 2.2903% | 8.6926% | 32.8790% |
| test | France | 2,262 | 3,098 | 1.19406% | 1.4908% | 5.1320% | 24.2719% |

The median relative collision burden is extremely stable between train and test for the labeled countries: US 0.01783% -> 0.01810% (1.015x), India 0.26914% -> 0.26667% (0.991x). France is qualitatively different: its median best address-number DF is 4.48x India's test-relative burden and 65.98x the US test burden. Number-only retrieval is therefore especially collision-prone for unseen France.

### Rare token types are not the same as rare evidence for typical records

India-train address-number token types look superficially attractive: 39.68% occur in one record, 74.68% have DF<=10, and 98.04% have DF<=1000. Yet only 2.17% of India records have any address number with DF<=10 and only 30.83% have one with DF<=1000. The common-number mass dominates records despite a long tail of rare types.

The same distinction matters in France: 77.41% of address numeric token types have DF<=10, but only 1.49% of French records contain such a number. A token-type histogram alone would badly overstate usable retrieval selectivity.

### Numeric shape differs strongly by country

Address digit-run occurrence shares:

| Country/split | 1 digit | 2 digits | 3 digits | 4 digits | 5 digits |
|---|---:|---:|---:|---:|---:|
| US train | 8.20% | 13.84% | 32.14% | 37.18% | 8.55% |
| India train | 37.91% | 31.80% | 25.62% | 4.47% | 0.15% |
| US test | 8.18% | 13.82% | 32.18% | 37.18% | 8.55% |
| India test | 37.89% | 31.89% | 25.54% | 4.48% | 0.15% |
| France test | 25.34% | 60.14% | 13.41% | 0.68% | 0.40% |

US and India train/test profiles are nearly invariant, while France is dominated by two-digit runs. This supports country/source-aware DF gating rather than a universal numeric-token policy.

Additional hazards:

- India addresses contain more numeric structure per row: median 2 distinct runs, p95 4, p99 6, versus US median 1/p99 3 and France median 1/p99 2.
- Repeated identical numeric tokens occur in 6.56% of India-train and 6.59% of India-test address rows, versus about 0.19% US and 0.11% France. Retrieval scoring must deduplicate a token within a record instead of rewarding repetition.
- Leading-zero numeric occurrences are 1.69% India train and 1.73% India test, so numeric tokens must remain strings; integer coercion would destroy evidence.
- Very long digit runs (>=7) are uncommon overall but highest in India at about 0.06% of records, consistent with occasional phone-like/identifier-like hazards. A dedicated retrieval rule should not blindly treat all digit runs as house/unit numbers.
- Four-digit year-like values are non-negligible, especially US at about 1.75% of address numeric occurrences, another reason to use corpus DF and context rather than hard-coded number semantics.

## Error analysis / interpretation

1. Broad coverage, weak universal selectivity. Address numbers are present for more than 91% of India anchors and essentially all US/France anchors, but a raw number-only block would be noisy: median best DF is 2,377 for India train and 3,098 for France test.
2. US is the easiest numeric-retrieval regime. Three quarters of US-train records have an address number with DF<=1000; India is only 30.83% and France 24.27%.
3. France needs safer composition. The unlabeled French Source-1 distribution shows much higher collision burden and a heavy two-digit regime. A France-safe channel should combine the number with independent lexical evidence rather than infer that a matching number alone is strong identity evidence.
4. India has richer but repetitive numeric structure. Multiple number runs offer opportunities for composite keys and conflict features, but repeated tokens must not multiply evidence.
5. Train/test stability validates the descriptive signal. The labeled countries' numeric presence, relative median best-DF, run-length profile, and repetition behavior are stable across train/test, reducing concern that the result is an artifact of the training population.

## Risks

- This is Source-1-only forensics. It does not establish positive-pair stability, pair recall, retrieval precision, or macro F0.5 gain. Those require complete S2/S3 inventories and supplied positive links.
- Country-local Source-1 DF is a feasibility proxy, not the production blocker frequency, which is computed over pooled S2+S3 targets. R007 must measure target-source DF and exact cap competition before promotion.
- Numeric tokens are heterogeneous: house/unit numbers, postcodes, years, phone-like strings, and identifiers. No semantic type is inferred here.
- France has no labels; all France statements are unlabeled distribution diagnostics only.

## Recommendation

FOLLOW-UP. The census supports continuing R007/M003, but with a narrower design than number-block-everything:

- prioritize address numeric tokens; name-number evidence is niche;
- keep digit runs as strings and deduplicate within records;
- use source/country/field DF gating;
- favor composite probes such as number + discriminative name fragment or number + rare address word, especially in India and France;
- treat number disagreement as a matcher conflict feature, where existing F005 hard-negative evidence is already strong;
- require exact same-slice R007 measurement of marginal recovered positives, added candidates, pair/entity/all-matches recall, blocking oracle, country/source slices, and candidate counts before integration.

## Follow-up tasks

1. Recover R007 on the private/Modal full target inventory and test country+field+DF-gated address-number blocks plus composite number+lexical probes.
2. M003 should separately test rare-number agreement/conflict features without changing retrieval, preserving retrieval recall/oracle.
3. Use French Source-1 collision burden only to choose conservative inference-safe defaults; do not fabricate French labels.
