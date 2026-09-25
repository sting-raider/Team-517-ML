# I017 — Internal F0.5 scorer parity audit

## Hypothesis

The internal per-anchor F0.5 implementation and retrieval-oracle diagnostics should match the published competition metric semantics on exhaustive small set-valued cases. Any mismatch would invalidate experiment comparisons.

## Change

No production scoring logic changed. Added `tests/test_metrics_parity.py` as an independent regression suite covering exhaustive set enumeration, singleton behavior, entity-level macro averaging, retrieval metric denominators, and blocker-oracle semantics.

## Protocol

Tier 0/1 research-integrity audit on synthetic sets only. No challenge labels, confirmation/frozen holdout, leaderboard feedback, or external entity data were consumed.

Audited:
- `src/ber/metrics.py` on main `2a2ae6e`
- the published count equation recorded in `RULES_INSIGHTS.md`
- the supplied organizer `utils/validate_submission.py` fetched from the shared Drive

Commands/checks:

```bash
PYTHONPATH=src python -m unittest tests.test_metrics tests.test_metrics_parity -v
python utils/validate_submission.py --matching <synthetic-duplicate.tsv> --test-dir <synthetic-test-dir>
```

The exhaustive parity test enumerates all truth/prediction subsets of a four-ID universe: 256 set pairs. Each internal score is compared independently against both the TP/FP/FN count formula and the precision/recall F0.5 formula.

## Results

- Existing + new metric tests: **9/9 PASS** in the local Python runtime.
- Exhaustive row-score cases: **256/256 agree** with both independent formulas.
- Maximum observed floating discrepancy in the independent exhaustive check: approximately **1.11e-16**.
- Published worked example remains `5/7`.
- Singleton convention is correct: empty truth + empty prediction = 1; empty truth + nonempty prediction = 0.
- Macro averaging is correctly per Source-1 entity, not pair-weighted.
- Blocking oracle correctly scores the best possible subset of retrieved true links and therefore ignores false candidates while retaining singleton score 1.
- Organizer validator synthetic duplicate-ID smoke exits nonzero and rejects repeated IDs in a row, as documented.

Competition metric baseline/result: unchanged. I017 does not re-evaluate or alter the selected 0.928835 confirmation score.

## Error analysis

- **No official-score formula defect found.** The compact denominator `0.25*|T| + |P|` is algebraically identical to `1.25*TP + FP + 0.25*FN`.
- `candidate_pair_recall` is global true-link recall.
- Historical `candidate_entity_recall` is **mean fractional true-link recall per positive entity**, matching the repo's phrase “per-entity recall.” It is *not* the different statistic “fraction of positive entities with at least one retrieved true link.” This is a naming/documentation ambiguity, not a calculation error.
- `all_matches_retrieved_rate` is the stricter fraction of positive entities whose entire truth set is present.
- The in-memory scorer converts truth/predictions to sets. Thus duplicate IDs do not alter `row_score`; the organizer submission validator separately rejects duplicate IDs. That separation is acceptable only if official artifact validation remains mandatory.
- `evaluate` iterates the supplied truth universe, so extra prediction keys outside that universe are not included in macro scoring. The official validator separately rejects unexpected Source-1 rows. Again, artifact validation is a required boundary, not something the metric function itself enforces.

## Interpretation

The core competition scorer is trustworthy under the published equation and singleton convention, and the existing headline model/retrieval scores are not invalidated by I017. The strongest useful outcome is a regression guard against future “small cleanup” edits to metric code, the traditional birthplace of competition disasters.

The retrieval diagnostics are internally consistent, but reports should describe `candidate_entity_recall` explicitly as mean per-positive-entity fractional recall so agents do not reinterpret historical numbers as any-match entity coverage.

## Risks

- The organizer-supplied helper validates submission formatting and IDs; it explicitly does **not** compute leaderboard score. Therefore parity is against the published scoring equation, not an executable organizer scorer.
- The synthetic exhaustive universe covers set semantics, not every possible floating cardinality. Algebraic equivalence removes cardinality-dependent formula uncertainty.
- Regression tests cannot detect a future pipeline that supplies the wrong truth/prediction mappings before scoring.
- In-memory set deduplication can hide malformed list duplicates if artifact validation is skipped.

## Recommendation

**PROMOTE**

Merge the regression tests. Do not change historical metric fields or recalculate reports. Clarify the meaning of `candidate_entity_recall` in future retrieval reports, and keep the supplied submission validator as a mandatory final artifact gate.

## Follow-up tasks

- Add an explicit any-match entity-coverage diagnostic only if retrieval agents need that distinct statistic; preserve the historical field for comparability.
- Keep metric tests and official format validation separate so one cannot be mistaken for the other.
