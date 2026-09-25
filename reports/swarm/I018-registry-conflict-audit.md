# I018 — Experiment-registry merge-conflict pressure audit

## Hypothesis
Requiring every experiment branch to edit the single `experiments/REGISTRY.tsv` creates a systemic integration hotspot in the current swarm. If most live PRs insert one row at the same location, the registry becomes disproportionately likely to require manual conflict resolution and to lose or duplicate experiment rows during rapid integration.

## Change
No model, retrieval, metric, dataset, or production inference behavior was changed.

This task audited live GitHub pull-request metadata and representative file patches only.

## Protocol
Audit snapshot: 25 Sep 2026, approximately 17:15 UTC.

Repository: `sting-raider/Team-517-ML`.

Procedure:
1. enumerate every open PR returned by GitHub (`is:pr is:open`);
2. fetch the complete changed-filename list for each PR;
3. count exact-path overlap for `experiments/REGISTRY.tsv` and `reports/swarm/`;
4. inspect representative `experiments/REGISTRY.tsv` patches from PRs #155, #129, #120, and #38;
5. compare against latest `main`, whose registry contains only the header row.

No challenge records, confirmation anchors, frozen holdout, predictions, or leaderboard feedback were read.

## Results
Open PRs in the audit snapshot: **68**.

- PRs modifying `experiments/REGISTRY.tsv`: **67 / 68 = 98.53%**.
- PRs modifying at least one `reports/swarm/` file: **67 / 68 = 98.53%**.
- The sole exception was PR #149 (R004), which at the snapshot contained only a workflow and experiment helper and had not yet checkpointed its required report/registry row.
- The report directory itself is not a comparable hotspot because nearly all reports use experiment-specific filenames.
- No other exact file observed in the audit approached the registry's overlap. The next repeated implementation/documentation paths were only low-single-digit overlaps (for example `MODAL.md` and `src/ber/predict.py` appeared in three open PRs in the inspected set).

Representative registry patches from four unrelated PRs (#155 F007a, #129 R009a, #120 I016, #38 I005) all have the same shape:

```diff
@@ -1 +1,2 @@
 <registry header>
+<one experiment row>
```

Thus these branches are not merely touching the same logical artifact; they are independently inserting different rows at the same one-line base location.

### Baseline vs observed coordination pressure

| Measure | Baseline / desired property | Observed |
| --- | --- | ---: |
| Open PRs | N/A | 68 |
| PRs touching central registry | isolated experiment metadata | 67 (98.53%) |
| Main registry data rows | should accumulate durable experiment history | 0 |
| Representative registry insert location | independent paths preferred | same post-header hunk in 4/4 checked PRs |
| Largest other exact-file overlap observed | low shared-file pressure | <=3 PRs |

The central registry therefore dominates cross-branch write overlap by more than an order of magnitude.

## Error analysis
This audit establishes **merge-conflict pressure**, not that every pairwise merge will necessarily conflict. Git's exact automatic-merge outcome depends on merge order and surrounding history.

The more important failure mode is operational: as soon as one experiment row lands on `main`, dozens of long-lived branches based on the header-only registry become stale at the same location. Each integration then needs reconciliation of experiment metadata in addition to its substantive code/report review. With 67 outstanding writers, accidental row loss, duplicate reconciliation, and merge-order mistakes become plausible.

The current contract also couples a required scientific record to a mutable shared aggregation file. That is unnecessary because each experiment already has a unique experiment ID and unique report path.

## Interpretation
The hypothesis is strongly supported. The registry is a swarm-wide serialization point.

This does not invalidate any experiment result. It does make the current handoff protocol scale poorly exactly when many disposable agents are active.

The smallest conflict-resistant design is:
1. each experiment writes one uniquely named immutable row fragment, e.g. `experiments/registry_rows/X008.tsv`;
2. a deterministic coordinator/helper validates the schema and rebuilds `experiments/REGISTRY.tsv` from fragments;
3. the consolidated TSV remains the human-friendly canonical view on `main`, but experiment branches stop editing it directly.

This preserves the existing schema and downstream readability while moving concurrent writes onto unique paths.

## Risks
- Existing 67 PRs will not become conflict-free retroactively.
- A fragment scheme needs duplicate experiment-ID validation so two branches cannot silently claim the same ID.
- A generated central registry must be deterministic and fail on malformed rows rather than silently skipping them.
- Until the protocol changes, coordinators must reconcile `experiments/REGISTRY.tsv` carefully when merging current PRs.

## Recommendation
**FOLLOW-UP / HIGH PRIORITY THROUGHPUT FIX.**

Create one bounded infrastructure task to implement per-experiment registry fragments plus a deterministic rebuild/validation helper, then update `AGENTS.md` / `SWARM_PROMPT.md` for new agents. Do not rewrite existing experimental PRs solely for this migration; reconcile their current rows during integration.

## Follow-up tasks
One follow-up is justified: implement the fragment-and-rebuild mechanism with duplicate-ID/schema tests. No modeling follow-up is implied by this audit.
