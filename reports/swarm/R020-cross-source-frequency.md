# R020 — Cross-source posting-frequency suppression audit

## Hypothesis

Blocker v2 pools posting-list frequency across Source 2 and Source 3 before applying both its frequency cutoff and its IDF-like retrieval weight. A key can therefore be rare and highly discriminative in one target source but be removed or downweighted because the same key is common in the other target source.

## Change

No production retrieval behavior was changed.

This task adds a dependency-free mathematical reference helper and focused tests for the current pooled-frequency semantics versus source-specific frequency accounting.

## Protocol

Repository baseline: latest main at task start, commit 2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460.

Static audit target: src/ber/blocking.py.

The current index first creates raw key postings from every record with source > 1:

    SELECT rowid AS rid, hash(country,k) AS key
    FROM split, unnest(block_keys(n,a))
    WHERE source>1

It then computes:

    SELECT key,count(*) AS freq
    FROM split_rawkeys
    GROUP BY key

The grouping includes country inside the hash but does not include target source. The same pooled frequency is then used to:

1. discard every key whose pooled frequency exceeds 1000; and
2. score every surviving hit with ln(10000001 / freq).

Synthetic validation isolates those two operations. It does not use challenge rows or labels.

Command:

    PYTHONPATH=src pytest -q tests/test_cross_source_frequency_audit.py
    PYTHONPATH=src python -m ber.cross_source_frequency_audit

Result: 8/8 tests passed in 0.13 seconds.

Full S2/S3 measurement was not run because this ChatGPT Drive handoff rejects train_source2.tsv (489,301,488 bytes) and train_source3.tsv (503,705,637 bytes), which exceed its 256 MiB per-file limit. No sample was substituted.

## Baseline context

The current selected blocker at cap 640 has confirmation candidate pair recall about 0.947246 and blocking-oracle macro F0.5 about 0.980951. These existing values are context only. R020 did not consume or tune on confirmation data.

## Results

### 1. A rare key in one target source can be deleted by the other source

Consider one key with 1,001 S2 postings and exactly 1 S3 posting.

Current pooled frequency is 1,002, so the key fails the freq<=1000 filter and is absent from the index for both sources.

Under source-specific accounting, the S3 posting has frequency 1 and is maximally selective, while only the S2 side exceeds the cutoff.

Thus current pooling can remove the strongest possible source-specific rare-key evidence solely because that key is common in the other source.

### 2. Two individually acceptable posting lists can jointly fail the cutoff

With 600 S2 postings and 600 S3 postings, both source-specific lists satisfy freq<=1000. Their pooled frequency is 1,200, so blocker v2 discards both.

This is pure cross-source coupling: neither source individually violates the intended posting-list bound.

### 3. Surviving rare evidence can be heavily downweighted

With 1 S2 posting and 999 S3 postings, pooled frequency is exactly 1,000 and the key survives.

For the unique S2 posting:

    source-specific weight = ln(10000001 / 1)
    pooled weight          = ln(10000001 / 1000)
    difference             = ln(1000)
                           = 6.907755...

So the unique S2 match loses about 6.908 retrieval-score points because of unrelated S3 frequency.

The corresponding S3 loss is only about 0.001. The coupling is therefore strongly asymmetric precisely when a token is rare in one source and common in the other.

### 4. Source-specific accounting has useful monotonicity properties

Property tests over 10,000 random frequency pairs verified:

- whenever a pooled key is eligible, every nonempty source-specific posting list is also individually eligible;
- source-specific IDF-like weight is never lower than pooled weight for that source;
- if the other source has zero postings, source-specific and pooled weights are identical.

Therefore splitting frequency accounting by target source cannot make a currently retained key fail the same numeric cutoff due to frequency alone. It can only preserve existing source postings or recover/downweight them differently. Candidate-count and ranking effects still require empirical measurement.

## Interpretation

The blocker currently treats target-source frequency as if S2 and S3 were one corpus for key selectivity, despite later exposing target source as a matcher feature and despite source-specific corruption patterns being a central project concern.

The cutoff effect is the highest-confidence risk: useful evidence can be removed before candidate generation. The weighting effect is subtler but potentially large because retrieval is itself a CatBoost input and also controls the final candidate ranking.

This mechanism is separate from R019. R019 concerns competition between already-generated S2/S3 candidates at the final cap. R020 concerns whether source-specific evidence is suppressed before those candidates even exist.

## Risks and red-team checks

- No competition-score gain is claimed.
- The exact prevalence of cross-source frequency asymmetry is unknown without complete S2/S3 access.
- Source-specific frequency can enlarge the index because some postings currently discarded by pooled freq may become eligible. Runtime, memory, and candidate fanout must be measured.
- More candidates do not automatically improve the organizer's candidate-list review; evaluation must compare recall gain against added candidate cost.
- A globally common key may be intentionally downweighted even if rare in one source. Empirical same-slice oracle results must decide whether source specificity is beneficial.
- The synthetic helper contains no challenge IDs or records and uses no external identity information.
- No confirmation/final holdout was consumed.

## Recommendation

**FOLLOW-UP.**

On a full-data runtime, implement an experimental source-specific posting-frequency index while preserving the current blocker as baseline. Compare on the exact established calibration anchors at identical final caps.

Required measurements:

- number/fraction of query keys lost only because pooled freq >1000 while at least one source-specific freq <=1000;
- anchors affected and target-source distribution;
- marginal candidate pairs created;
- marginal true positives recovered;
- pair recall, entity recall, all-matches-retrieved rate, and blocking-oracle macro F0.5;
- candidate count mean/p50/p90/p99/max;
- US/India slices and S2/S3 slices;
- index size, build time, retrieval time, and memory;
- ablate source-specific cutoff from source-specific weighting so any gain is attributable.

Only promote if the oracle/recall gain survives the candidate-budget and runtime tradeoff on the same anchors.
