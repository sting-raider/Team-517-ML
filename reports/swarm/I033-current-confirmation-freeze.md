# I033 — Integrate confirmation freeze with current INT003 paths

## Recommendation

**PROMOTE.**

The current confirmation policy now fails closed across the selected INT002/INT003 architecture rather than guarding only the historical `ber.confirm` CLI. All four already-inspected 5,000-anchor windows from offsets 30,000 through 50,000 are ledgered, the current expanded-fit search range is forbidden for ad-hoc contiguous confirmation, and both Modal feature-cache access and score observation require explicit reasoned reproduction of the exact historical window.

No confirmation inference, fresh holdout consumption, model scoring, threshold tuning, retrieval change, or leaderboard feedback occurred in this task.

## Evidence / motivation

I005R2 / PR #245 red-teamed the older I005 implementation in PR #38 and found four current-state gaps:

1. PR #38 recorded only the 30,000:35,000 and 35,000:40,000 consumed windows, while committed INT002 and INT003 reports prove that 40,000:45,000 and 45,000:50,000 were also inspected.
2. Selected-model confirmation moved to `v2.py` / `v3.py` plus `modal_v2.py` / `modal_v3.py`, bypassing the old guarded CLI.
3. Cached confirmation feature parts could be returned before any holdout check, and `confirm_model()` could score them repeatedly.
4. Current fitting uses fit-fold anchors from sample positions 50,001 through 200,000. After consuming all four contiguous 5k windows in the 30k:50k gap, blindly moving confirmation above 50k can overlap training.

I033 refreshes the policy against current main instead of merging the stale PR unchanged.

## Change

### Canonical ledger

`reports/CONFIRMATION_FREEZE.json` now records:

- forbidden development range: offset 0, size 30,000;
- forbidden current expanded-fit search range: offset 50,000, size 150,000;
- consumed 30,000:35,000 historical shortlist confirmation;
- consumed 35,000:40,000 selected submission-v1 confirmation;
- consumed 40,000:45,000 INT002 confirmation;
- consumed 45,000:50,000 INT003 confirmation.

The expanded-fit reservation matches current `v2.select_anchors()`, which admits fit-fold anchors at sample positions 50,001 through 200,000.

### Shared holdout contract

`src/ber/holdout.py` provides a stdlib-only policy layer:

- rejects invalid offset/size;
- rejects any overlap with forbidden ranges;
- rejects silent reuse of consumed windows;
- permits historical reproduction only for one exact consumed window plus a non-empty reason;
- rejects partial overlap even when reuse is requested;
- requires explicit `consume_new` plus reason for genuinely fresh legacy-CLI evaluation;
- atomically records a fresh consumption before downstream report output;
- provides `require_confirmation_reuse()` for current v2/v3 historical confirmation, which deliberately does not authorize a fifth fresh window.

### Current INT002 / INT003 materialization

`src/ber/v2.py` now authorizes confirmation before selecting any confirmation anchors. The selected-model training path is unchanged when `confirmation=False`.

`src/ber/v3.py` propagates the same authorization contract for its historical 45k:50k window.

Feature receipts preserve the explicit confirmation-reuse reason.

### Modal cache and score boundaries

`modal_v2.py` and `modal_v3.py` each enforce the same exact historical reuse policy twice:

1. **before checking or returning `ready.json`**, so an existing confirmation feature cache cannot bypass the guard;
2. **before `confirm_model()` loads probabilities or returns metrics**, so direct cached re-scoring cannot silently expose the holdout again.

The local `confirm` action itself also requires a non-empty `reason`.

The Modal image ships the canonical ledger at `/app/reports/CONFIRMATION_FREEZE.json`.

### Legacy CLI and documentation

`src/ber/confirm.py` no longer has a default confirmation window. It requires explicit offset/size and authorization, protects report overwrites, verifies requested label count, checks model-anchor overlap, and records fresh consumption before report output.

Routine `python -m ber.confirm` was removed from README reproduction instructions. README now documents the four consumed windows and the current 50k:200k training reservation.

## Protocol

Task / issue: I033 / #249  
Branch: `agent/i/I033-current-confirmation-freeze`  
Base audited: `f08c041b274e58ae900620ac714ec8a0a06f09b0`

Tier-0/1 evaluation-integrity task only. No challenge prediction metric is applicable.

Validation was deliberately dependency-light because this environment lacks DuckDB and an authenticated Modal execution lane.

### Exact branch readback

The final branch files were fetched back from GitHub and checked for the following invariants:

- exactly four consumed 5,000-anchor windows in 30k:50k;
- development 0:30k forbidden;
- expanded-fit 50k:200k forbidden;
- shared v2 selector invokes confirmation authorization before selection;
- v3 propagates the reuse reason;
- Modal v2 and v3 invoke authorization before `ready.json` cache access;
- Modal v2 and v3 guard `confirm_model()` score observation;
- both Modal confirmation reports record the holdout-guard action/reason;
- local Modal confirmation actions reject a blank reason;
- legacy CLI has no default offset/size;
- Modal image includes the canonical ledger;
- README no longer runs confirmation routinely.

Result: **all checked invariants PASS**.

### Policy boundary mirror

A dependency-light mirror of the exact interval/authorization semantics exercised nine adversarial boundary cases, including:

- development-boundary overlap;
- beginning/end of the 50k:200k forbidden training range;
- silent reuse of the 35k/40k/45k consumed windows;
- exact reasoned reuse;
- partial consumed-window overlap;
- first post-current-training fresh window at offset 200,000;
- fresh-window reason requirements.

Result: **9 / 9 PASS**.

The authored repository tests are:

- `tests/test_holdout.py`
- `tests/test_confirmation_guard_wiring.py`

They are stdlib-only, but this chat did not directly execute the GitHub branch checkout as a local repository, so this report does **not** falsely claim a normal `unittest discover` run. The branch readback and policy-semantic checks above were executed independently.

## Result

No score delta is claimed because no confirmation set was evaluated.

The integrity result is:

| Property | Before I033 | I033 |
|---|---|---|
| Consumed ledger through 50k | incomplete | complete |
| 50k:200k current fit search reserved | no | yes |
| legacy `ber.confirm` | default/replay-prone | explicit fail-closed |
| v2/v3 feature materialization | unguarded | exact reuse + reason |
| confirmation cache reuse | unguarded | guarded before cache access |
| direct confirmation scoring | unguarded | guarded before observation |
| routine README confirmation | present | removed |
| model/retrieval default behavior | current INT003 | unchanged |

## Error analysis / red-team checks

### Cache-before-guard regression

The most important ordering invariant is that `require_confirmation_reuse()` executes before checking `ready.json`. The wiring regression tests encode this explicitly for both Modal v2 and v3.

### Score-observation bypass

Materialization-only guarding is insufficient because a caller can score a previously generated cache directly. Both `confirm_model()` functions therefore independently require exact historical authorization.

### Fresh window after 50k

The current v2/v3 historical path refuses fresh confirmation altogether. The legacy CLI can authorize a genuinely fresh range only outside forbidden ranges and also checks the chosen model's anchor IDs before scoring.

### Partial overlaps

A window that mixes consumed and untouched anchors is rejected rather than treated as either reproduction or new evaluation.

### Failure after metrics exist

For legacy fresh consumption, the ledger is updated before report output. Once metrics exist in memory, the holdout is scientifically consumed even if writing the report later fails.

## Risks

1. No authenticated Modal smoke was run here. The guard code is source-validated and dependency-light, but one normal integration smoke should verify packaging/import paths without evaluating confirmation labels.
2. The freeze ledger is a Git coordination mechanism, not protection against a deliberately edited code path.
3. Any future change to the training-selection universe, especially `training_end`, must update the forbidden-range policy or replace interval reservation with a centrally validated exact anchor-universe contract.
4. Two isolated branches could still race to reserve a future fresh window before either ledger update merges. Fresh holdout consumption should remain a GitHub-owned, serialized coordinator action.
5. I033 does not make the already-consumed INT002/INT003 windows untouched again. It makes future reuse explicit and auditable.

## Recommendation

**PROMOTE** the current-main safety integration.

It changes no matcher, retrieval, threshold, or production scoring semantics. Its purpose is to prevent ordinary swarm workflows from silently converting historical confirmation into another tuning set. PR #38 should be superseded by this current-main implementation rather than merged independently.
