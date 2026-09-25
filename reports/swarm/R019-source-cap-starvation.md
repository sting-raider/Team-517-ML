# R019 — Joint-cap target-source starvation audit

## Hypothesis

Blocker v2 applies one final candidate cap jointly across Source 2 and Source 3. If one target source supplies enough higher-ranked candidates, it can consume the entire cap and remove every candidate from the other source before the matcher sees them.

## Change

No production retrieval behavior was changed.

This task adds a dependency-free reference audit for the final ranking semantics and focused tests for a possible source-floor policy. The helper exists only to make the failure mode precise and reproducible. It is not connected to the production blocker.

## Protocol

Repository baseline: latest main at task start, commit 2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460.

Static audit target: src/ber/blocking.py.

The production final selection is:

    row_number() OVER(
        PARTITION BY anchor
        ORDER BY retrieval DESC, t.entity_id
    ) <= cap

There is no target-source term in the partition or ranking. Therefore S2 and S3 compete for one shared cap.

Synthetic validation mirrors only this final ranking stage after retrieval scores have already been computed. It does not invent challenge labels or claim to reproduce the real score distribution.

Command:

    PYTHONPATH=src pytest -q tests/test_source_cap_audit.py
    PYTHONPATH=src python -m ber.source_cap_audit

Result: 7/7 tests passed in 0.16 seconds in the local Python runtime.

Full S2/S3 empirical validation was not run in this chat because the connected Drive handoff rejects train_source2.tsv (489,301,488 bytes) and train_source3.tsv (503,705,637 bytes), both above its 256 MiB single-file limit. No sample was substituted.

## Baseline context

The current selected blocker at cap 640 has confirmation candidate pair recall about 0.947246 and blocking-oracle macro F0.5 about 0.980951. Those existing metrics are context only; R019 did not consume or retune the confirmation set.

## Results

### 1. Joint capping can completely starve one target source

With two S2 candidates scoring 100 and 99 and one S3 candidate scoring 90 at cap 2, the production-equivalent joint ranking selects both S2 candidates. The matcher receives no S3 candidate.

A reference policy reserving one slot for each available target source selects one S2 and one S3 candidate while keeping the same total cap.

This proves the mechanism exists. It does not prove that the reference policy improves challenge recall.

### 2. Starvation can occur on exact retrieval-score ties

With candidates a_s2, b_s2, and z_s3 all scoring 100 at cap 2, the current deterministic entity_id tie-break selects a_s2 and b_s2. S3 disappears despite having equal retrieval evidence.

The source-floor reference selects a_s2 and z_s3.

This matters because source imbalance is not necessarily evidence that one source is lexically worse; the deterministic tie-break alone can decide source coverage.

### 3. A one-per-source floor has a tightly bounded effect

Randomized property testing over 500 deterministic mixed-source inventories verified that a source_floor=1 policy changes at most one selected candidate relative to global top-k when both sources are available.

If global top-k already contains both sources, the policy is a no-op. If only one source has any candidates, it does not waste capacity. With source_floor=0, the reference selector exactly matches global top-k in 200 randomized cases.

Thus a one-slot floor can be evaluated without increasing submitted candidate count. Its cost is the displacement of at most the weakest globally selected candidate needed to restore the absent source.

### 4. This is a retrieval allocation question, not a matcher fix

Once one source has been fully removed by the cap, no matcher, threshold, calibration rule, or expected-F0.5 decoder can recover its true links. The only remedies are retrieval/ranking allocation changes before the matcher.

## Error analysis

The synthetic cases identify four distinct regimes:

1. **Strict source dominance:** one source has higher retrieval scores and consumes the cap.
2. **Tie-driven starvation:** equal retrieval evidence is resolved by entity_id ordering, accidentally eliminating one source.
3. **Already balanced:** global top-k contains both sources; a one-slot floor changes nothing.
4. **Single-source availability:** the other source produced no candidate at all; a floor cannot manufacture evidence and must not reserve an empty slot.

The unresolved real-data question is how often regimes 1 and 2 occur on development anchors, and whether the missing source actually contains unretrieved positives often enough to justify displacement.

## Risks and red-team checks

- No competition-score gain is claimed.
- The synthetic helper mirrors only the final ranking semantics, not key generation or retrieval-score construction.
- A source floor could hurt if the displaced candidate is a true positive and the forced candidate is a false positive.
- Multiple true matches can come from one source, so a 50/50 quota would be unjustified. R019 tests only a minimal floor as a diagnostic.
- The organizer also favors smaller candidate sets. This reference policy preserves the same cap and therefore does not increase candidate-list size, but quality still requires full-data measurement.
- Record IDs are used only as deterministic synthetic tie-break labels, matching the blocker ordering. They are not predictive features.
- No external identity data, geocoding, directories, or French labels were used.

## Recommendation

**FOLLOW-UP.**

Do not change production blocking from R019 alone. On a runtime with full S2/S3 access, benchmark the current joint cap against source floors 1, 2, and 4 on the exact established development/calibration anchors and identical raw candidate union.

Required measurements:

- fraction of anchors whose capped pool contains only S2 or only S3 despite pre-cap hits from both;
- fraction of those anchors whose truth includes a link in the excluded source;
- candidate pair recall, entity recall, all-matches-retrieved rate, and blocking-oracle macro F0.5;
- candidate-count statistics, which should remain unchanged at fixed cap;
- US/India and target-source slices;
- number and score gap of displaced versus inserted candidates;
- marginal recovered positives per displaced candidate.

Only promote a source floor if those same-slice measurements beat joint ranking and the gain survives a separate robustness slice.
