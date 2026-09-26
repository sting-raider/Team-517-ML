# I005R2 — Red-team current confirmation-freeze policy

## Recommendation

**FOLLOW-UP / DO NOT MERGE PR #38 AS-IS.**

The original I005 holdout guard has sound basic interval semantics, but it is stale relative to current `main` and does not protect the actual INT002/INT003 confirmation pathways. Merging it unchanged would create a false sense of holdout safety.

No confirmation inference, new labels, candidate probabilities, model scoring, or fresh holdout window were consumed in this audit.

## Target

- Issue: #67 / I005R
- Target PR: #38, `agent/i/I005-confirmation-freeze`
- Current-main base audited: `f08c041b274e58ae900620ac714ec8a0a06f09b0`
- Target PR head: `279f1256fe8f55fce5c52f445c89030cd446370b`
- PR #38 relative to current main: 7 commits ahead / 10 behind, diverged.

## Scientific / integrity question

Does PR #38 still fail closed against accidental confirmation reuse or fresh-window contamination after the repository moved to INT002/INT003, expanded matcher fitting, Modal confirmation materialization, and cached confirmation features?

## What still works in PR #38

Static audit supports the original helper semantics:

- half-open interval overlap logic is correct for SQL `LIMIT size OFFSET offset` / sample-position windows;
- the development region 0:30,000 is rejected;
- exact reuse of one consumed range requires an explicit override and non-empty reason;
- partial overlap with consumed ranges is rejected;
- fresh disjoint ranges require explicit consumption and reason;
- invalid sizes/offsets fail closed;
- `register_consumption()` re-authorizes before append and atomically replaces the manifest file;
- registering consumption before report write is conservative if the later report write fails;
- README removal of routine `python -m ber.confirm` is directionally correct.

These findings do not require rerunning the target PR's authored tests to establish the current-live-state defects below.

## Material findings

### 1. The freeze manifest is stale by two fully consumed windows

PR #38 records only:

| Window | Status in PR #38 |
|---|---|
| 0:30,000 | forbidden development |
| 30,000:35,000 | consumed historical shortlist confirmation |
| 35,000:40,000 | consumed submission-v1 confirmation |

Current committed reports additionally prove:

- INT002 consumed **40,000:45,000** (hash positions 40,001–45,000), `reports/int002_depth10_confirmation.json`;
- INT003 consumed **45,000:50,000** (hash positions 45,001–50,000), `reports/int003_depth10_confirmation.json`.

Therefore the PR #38 manifest would classify both already-inspected windows as fresh.

That is a direct fail-open defect in the policy state, not merely missing documentation.

### 2. The active INT002/INT003 confirmation path bypasses `ber.confirm`

PR #38 protects `src/ber/confirm.py`, but current selected-model confirmation is implemented elsewhere:

- `src/ber/v2.py::select_anchors(..., confirmation=True, confirmation_start=40000)`
- `src/ber/v3.py::materialize(..., confirmation=True)`, delegating to v2 with start 45,000
- `modal_v2.py::make_features(..., confirmation=True)` + `confirm_model()`
- `modal_v3.py::make_features(..., confirmation=True)` + `confirm_model()`

These paths do not import or consult PR #38's holdout policy.

The repository search on current main contains no `CONFIRMATION_FREEZE` reference at all.

So even if PR #38 were merged without conflicts, protecting only the historical CLI would not establish a repository-wide confirmation boundary.

### 3. Cached confirmation features allow silent repeated scoring

The Modal feature builders return an existing `ready.json` confirmation cache before any prospective anchor-selection guard would execute.

Separately, `confirm_model()` loads the confirmation feature artifacts and scores them again without an authorization check.

Therefore adding a guard only inside `v2.select_anchors()` would still be insufficient: an already-materialized confirmation cache can be repeatedly inspected without reauthorization.

A correct policy needs a guard at the **observation/scoring boundary** as well as at materialization.

### 4. The old “choose a fresh disjoint window” policy is no longer safe after 50,000

Current v2 fitting deliberately expanded beyond the development block:

`sample_position <= 30,000 OR (sample_position > 50,000 AND sample_position <= 200,000)`

with only `fold(entity_id) == 'fit'` retained in the expanded region.

I024 independently reconstructed the selected model fit population:

- 108,115 fit anchors total;
- 17,990 original-development fit anchors;
- **90,125 expanded fit anchors**;
- zero fit anchors in 30,001–50,000.

All four 5,000-anchor contiguous windows in the protected 30,000:50,000 gap have now been consumed.

A naïve next window at 50,000:55,000 is therefore not an untouched confirmation population: it can contain expanded-fit anchors. The v2/v3 confirmation materialization path does not independently compare against the trained model's anchor IDs.

For a conservative contiguous-window policy, the entire **50,000:200,000** expanded-training search range should be treated as forbidden unless the confirmation selector explicitly filters out every training anchor and preserves a separately preregistered evaluation universe.

### 5. PR #38 is operationally stale against current main

The target branch is diverged, 10 commits behind current main, and predates v2/v3 confirmation infrastructure. Its report's statement that the two existing 5k windows are the canonical consumed state is no longer true.

This is not a reason to discard the helper logic; it is a reason to refresh and integrate it at the current architecture rather than merge the historical patch unchanged.

## Risk model

The important failure is not that a malicious caller can edit the manifest. Repository conventions cannot prevent deliberate sabotage.

The realistic failure modes are ordinary swarm behavior:

1. an agent runs current `modal_v3.py ... action=confirm` again while comparing a tiny change;
2. an agent changes `confirmation_start` to 50,000 believing it is the next fresh window;
3. an agent reuses cached confirmation feature parts and invokes `confirm_model()` repeatedly;
4. an old PR is merged whose manifest omits later consumption.

All four can occur without any explicit intent to leak or tune on holdout.

## Required remediation

Before I005 can be promoted on current main:

1. **Refresh the ledger** with all four consumed 5k windows:
   - 30,000:35,000
   - 35,000:40,000
   - 40,000:45,000
   - 45,000:50,000
2. **Reserve current training space.** Conservatively forbid 0:30,000 and 50,000:200,000 for contiguous confirmation selection, or encode exact training-anchor exclusion in a centrally validated selector.
3. **Guard all active entrypoints**, not only `ber.confirm`:
   - v2/v3 feature materialization;
   - Modal `confirm` local actions;
   - `confirm_model()` / equivalent score-observation functions.
4. **Guard cached reuse.** A confirmation feature receipt must carry window identity and authorization state, and scoring an already-consumed cache must still require explicit reuse + reason.
5. **Fail closed before observations escape.** Fresh-window consumption must be durably recorded before metrics are returned/printed/written somewhere an agent can inspect.
6. **Rebase onto current main** and add regression tests for:
   - INT002 and INT003 windows recognized as consumed;
   - 50,000:55,000 rejected under current training reserve;
   - direct cached `confirm_model` reuse rejected without explicit authorization;
   - exact historical reproduction allowed only with explicit reason;
   - partial-overlap and boundary cases preserved.

## Suggested architecture

Keep PR #38's pure `holdout.py` interval helper, but make authorization a shared confirmation-run contract rather than a CLI-specific check.

A practical design is:

- one canonical freeze/consumption ledger;
- one function that returns a structured authorization receipt for `{window, model/config identity, action, reason}`;
- materialization stores that receipt in `ready.json`;
- scoring validates the receipt again and requires explicit reuse for consumed windows;
- fresh consumption is atomically persisted before score output becomes observable.

The policy should be enforced at both materialization and scoring because either stage can be cached/replayed independently.

## Evaluation

Tier-0 static/source red-team only.

No model metric is appropriate. The result is a correctness finding:

- original PR interval-helper logic: **directionally sound**;
- current ledger completeness: **FAIL**;
- current active-path coverage: **FAIL**;
- current post-50k fresh-window assumption: **FAIL**;
- safe-to-merge PR #38 unchanged: **NO**.

## Recommendation

**FOLLOW-UP.** Preserve and refresh the I005 helper, but do not merge PR #38 unchanged. The next implementation should be based on current main and prove fail-closed behavior for current Modal v2/v3 confirmation and cached-feature reuse.

This finding is evaluation-safety infrastructure. It does not change the validity of already-recorded INT002/INT003 scores; it changes how those windows must be treated going forward.
