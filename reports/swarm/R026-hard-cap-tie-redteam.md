# R026 — hard-cap tie membership red-team

## Hypothesis

Current retrieval paths use record IDs only as deterministic tie-breakers, but at a hard candidate cap that tie-break can become a model-relevant eligibility decision: two candidates with identical permitted retrieval evidence can be included or excluded solely because their IDs sort differently.

This is distinct from R025 / PR #178, which found and fixes entity-ID ordering in the **numeric RRF weight** itself.

## Change

No production retrieval behavior was changed.

This branch adds:

- `tools/audit_cap_ties.py`: a deterministic pure-Python audit helper for current exact-cap semantics and an ID-invariant boundary-tie reference policy.
- `tests/test_retrieval_cap_ties.py`: five focused tests covering ID permutation, boundary-tie inclusion, non-tied parity, secondary-evidence tie resolution, and invalid caps.

Implementation commits:

- helper: `00e446aee42dd629ce1bac8c5cb1da6d7fa0ec09`
- tests: `1083c526ef9c88297b2db8e6a6a25c0387f0743a`

## Protocol

Source baseline: latest main at task start, `f87b43dff37991a9ffa7163f37dc5b5ec0ce794d`.

Audited paths:

1. `src/ber/blocking.py::candidates`
2. `src/ber/retrieval_v3.py::source_candidates`
3. `src/ber/retrieval_v3.py::char_candidates`
4. `src/ber/retrieval_v3.py::experiment` final RRF fused cap

All four use `row_number()` with `entity_id` after the evidence score when enforcing a hard candidate count. The first three order by retrieval score then entity ID; the fused pool orders by RRF score then entity ID.

R025 / PR #178 was inspected separately. It replaces ID-sensitive ordinal ranks used to **compute RRF weights** with score-only dense ranks, but explicitly leaves hard-cap ID tie membership as follow-up. Therefore R026 is non-duplicative.

Synthetic benchmark:

- cap = 160
- 158 candidates have strictly higher retrieval scores
- 5 physical candidates have identical boundary score and identical `hits`
- only the IDs assigned to those five physical candidates are permuted
- compare current exact-cap semantics against an ID-invariant policy that includes the complete evidence tie at the cap boundary
- separately verify a no-boundary-tie case and a case where legitimate secondary `hits` evidence resolves the score tie

Commands:

```bash
python tools/audit_cap_ties.py
python -m unittest tests/test_retrieval_cap_ties.py -v
```

Five tests passed. The unittest body reported 0.004 s; no challenge data or model inference was required.

No confirmation/frozen window, leaderboard feedback, external identity data, or raw challenge rows were used.

## Results

### Source audit

| Path | Current hard-cap order | ID can affect membership at a score tie crossing cap? |
|---|---|---|
| blocker v2 | retrieval DESC, entity_id | Yes |
| source-aware lexical | retrieval DESC, entity_id | Yes |
| character retriever | retrieval DESC, entity_id | Yes |
| final character-RRF fusion | score DESC, entity_id | Yes |

The query-key selection logic also has deterministic ordering, but it orders by corpus frequency and key text rather than record ID; R026 does not flag that path.

### Synthetic boundary case

| Metric | Current exact cap | Boundary-tie reference |
|---|---:|---:|
| Requested cap | 160 | 160 |
| Selected candidates | 160 | 163 |
| Physical membership symmetric difference after ID permutation | **4** | **0** |
| ID-invariant | No | **Yes** |

With 158 candidates above the boundary and five fully tied candidates competing for two remaining slots, reversing only the IDs assigned to the tied physical candidates swaps four physical candidates in/out of the current candidate set.

The boundary-tie reference keeps all five tied candidates, producing 163 candidates: +3 above the nominal cap, or +1.875% for this constructed anchor.

### No-boundary-tie parity

With 200 candidates having strictly ordered evidence scores, both policies select the identical top 160 and ID permutation changes nothing. A tie-safe policy therefore need not perturb anchors whose cap boundary is unambiguous.

### Legitimate secondary evidence

In a second synthetic case the five candidates tie on retrieval score but split on `hits`: two have 3 hits and three have 2. Treating `(score, hits)` as the evidence tuple resolves the constructed boundary exactly at 160 while remaining ID-invariant.

That is a mechanism demonstration, not a recommendation to adopt `hits` blindly. R022 / PR #112 showed that blocker hit counts can include correlated/double-counted evidence, including deterministic `h:`/`z:` overlap for single-number addresses.

## Error analysis

1. **The defect is conditional.** ID ordering affects membership only when an evidence tie intersects the cap boundary. R026 does not know how often that happens on the full target inventory.
2. **R025 is necessary but not sufficient for complete ID-invariance.** Dense score-only RRF weights remove ID dependence from the fusion weight, but base/character candidate membership can already have been ID-selected at their own hard caps, and the final fused hard cap still has an ID tie-break.
3. **Exact cap and complete invariance are incompatible for fully indistinguishable candidates.** If more candidates share the complete permitted evidence tuple than there are remaining slots, any exact-size strict subset needs an arbitrary discriminator. Using record ID makes that discriminator identity-derived. Including the full boundary tie avoids the arbitrary choice but makes the cap a soft upper bound.
4. **Secondary evidence can reduce overflow, not eliminate the fundamental case.** `hits`, channel count, source balance, or other permitted evidence may break many ties, but a residual full-evidence tie can still cross the cap.
5. **Candidate-size cost matters.** Organizer guidance favors smaller candidate sets. Boundary-tie inclusion is therefore not free and needs measured tie prevalence / overflow before production adoption.

## Interpretation

The current hard-cap tie-break is not merely cosmetic determinism. At a tied boundary it determines which record IDs are even eligible for matching, so ID order can alter candidate recall and the blocking oracle despite identical textual/retrieval evidence.

This is narrower than the rejected INT001 ordinal-rank feature: the ID is not exposed as a numerical matcher feature. But it is still an identity-derived decision in the retrieval path and should not be assumed harmless under the repository rule that record IDs must not become predictive evidence.

The cleanest ID-invariant reference is score/evidence `rank() <= cap`, which includes the complete boundary tie. An evidence-aware secondary ordering may keep the candidate count closer to the nominal cap, but every proposed secondary signal must be justified as real matching evidence rather than an arbitrary replacement for ID order.

## Risks

- **No full-data prevalence measurement.** Train Source 2/3 exceed this chat's 256 MiB Drive raw-transfer limit, and this runtime has no private Modal-volume access. R026 therefore does not claim that boundary ties are common or that fixing them improves macro F0.5.
- **No candidate-cost estimate.** The +1.875% overflow is a constructed example, not an expected production increase.
- **Interaction with R022.** Using `hits` as a secondary tie-break may reinforce correlated-key inflation.
- **Interaction with R025/R024.** Any matcher-coupled rerun should regenerate candidate pools after R025's dense-rank fix and should measure hard-cap boundary ties before declaring the path fully ID-independent.
- **No leaderboard inference.** No public/private score is used as truth.

## Recommendation

**FOLLOW-UP.**

Do not change the production cap policy from this synthetic result alone. Before R024/INT003 promotion, run one full-inventory paired audit on the exact same development anchors:

1. count anchors where a score/evidence tie crosses each hard cap;
2. report boundary tie-group sizes and candidate overflow under `rank() <= cap`;
3. measure pair/entity/all-matches recall and blocking-oracle macro F0.5 for current ID-tied exact cap vs boundary-tie inclusion;
4. report India/US slices and mean/p90/p99 candidate counts;
5. if testing `hits` or channel provenance as secondary evidence, compare it separately because R022 makes correlated-hit behavior a known risk.

The important immediate coordination rule is simpler: R024 should not call the corrected RRF path fully ID-invariant merely because R025 removed ID order from the numeric RRF rank.

## Follow-up tasks

No new issue is required unless R024 does not absorb the full-data tie-prevalence check. The existing matcher-coupled retrieval integration is the right place to measure the real cost/benefit.
