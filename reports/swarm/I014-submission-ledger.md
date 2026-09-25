# I014 — Leaderboard submission ledger

## Hypothesis

A small committed submission ledger that separates immutable artifact provenance
from leaderboard feedback will reduce submission confusion and make it harder to
accidentally use leaderboard feedback as training/evaluation evidence while the
swarm produces many candidate variants.

## Change

Added:

- `submissions/LEDGER.tsv`: durable metadata ledger, seeded with the already
  documented first full Modal cap-160 export.
- `submissions/README.md`: lifecycle and anti-leakage rules.
- `src/ber/submission_ledger.py`: stdlib-only validator/updater.
- `tests/test_submission_ledger.py`: synthetic regression suite.
- `PROJECT_DECISIONS.md`: persistent rule requiring immutable provenance for
  rows marked `SUBMITTED`.

No raw challenge records, predictions, checkpoints, credentials, or row-level
diagnostics are stored in the ledger.

## Protocol

Tier-0/1 infrastructure task on main
`2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`.

Inputs were committed aggregate/provenance facts only:

- `README.md`
- `PROJECT_DECISIONS.md`
- `reports/candidate_budget.json`
- `reports/submission_v1_confirmation.json`

No training labels, confirmation entities, or leaderboard feedback were read or
changed. The Python/container backend in this chat returned `ClientError`, so
the authored test suite could not be executed here and no passing-test claim is
made.

## Baseline

Before I014 there was no canonical repository ledger tying one leaderboard
upload to all of:

- a stable submission ID/status
- exact code SHA
- model-config SHA-256
- matching-output SHA-256
- candidate-output SHA-256
- candidate budget / threshold
- same-config local evaluation protocol and metrics
- aggregate test export counts
- leaderboard feedback explicitly marked as informational only

This creates an avoidable coordination risk once several branches produce
plausible submissions.

## Results

### Ledger contract

A `SUBMITTED` row now requires:

- UTC submission time
- 40-character Git code SHA
- model-config SHA-256
- `matching_results.tsv` SHA-256
- `candidate_pairs.tsv` SHA-256

The validator rejects duplicate submission IDs, malformed SHA/digest fields,
non-finite or out-of-range scores, negative counts, local metrics without an
explicit local protocol, and leaderboard scores attached to non-submitted rows.

Any row containing `public_score` or `private_score` must carry
`feedback_usage=informational_only`.

### First full export seeded without inventing provenance

The currently documented full Modal export was entered as
`modal_parallel_v1_cap160` with status `GENERATED`, not `SUBMITTED`.

Committed context for that row:

- candidate cap: 160
- threshold: 0.5750000000000002
- local protocol: 4,389-anchor cap-160 calibration
- local macro F0.5: 0.9271965622202124
- candidate pair recall: 0.9253076721654884
- mean candidates: 142.18204602415128
- p90 candidates: 160
- full test anchors: 1,732,544
- full test candidate pairs: 256,724,515
- full test predicted matches: 5,881,092

The repository does not currently contain an immutable receipt proving the exact
code/config/output hashes for that historical export, so those fields remain
blank. The helper deliberately forbids changing the row to `SUBMITTED` until
they are supplied from the actual artifacts. This avoids retroactively inventing
provenance.

The independent cap-640 confirmation macro F0.5 (0.9288349532) is **not** copied
into this cap-160 row, because it is not a same-configuration measurement.

### Feedback isolation

Leaderboard scores are stored only as provenance. The helper provides a
`record-score` operation that can update an already-`SUBMITTED` row and
automatically marks the score usage `informational_only`.

The module is standalone and is not imported by blocker, matcher, threshold,
training, or evaluation code.

## Error analysis

The schema addresses several concrete failure modes:

- **Wrong output attributed to a score:** prevented by mandatory output hashes
  for `SUBMITTED` rows.
- **Wrong code/model attributed to an upload:** prevented by mandatory code and
  config hashes.
- **Two agents reuse one human-readable run name:** duplicate
  `submission_id` is rejected.
- **Calibration metric from another candidate cap copied onto a submission:**
  protocol is explicit; the seed row demonstrates leaving incompatible
  confirmation evidence out.
- **Public leaderboard feedback quietly becomes a tuning signal:** feedback
  fields are explicitly marked informational-only and physically separated
  from local evaluation fields.
- **Historical unknowns filled from memory:** allowed only under `GENERATED`;
  a row cannot become `SUBMITTED` with missing immutable receipt fields.

## Risks

- The Python regression suite was authored but not executable in this session
  because both container/Python backends returned `ClientError`.
- The ledger cannot stop a human from making a bad modeling decision outside
  code review. It makes the provenance and intended use explicit and
  reviewable; it is not a magical anti-overfitting force field.
- The first historical export still lacks immutable committed hashes. That is
  correctly represented as missing rather than guessed.

## Recommendation

**FOLLOW-UP.**

Adopt the ledger contract now, but keep the PR in draft until the focused
stdlib test suite is executed in a healthy Python environment. Before any future
leaderboard upload, create/complete its ledger row from the exact artifacts and
Git SHA first, then record returned leaderboard scores only as informational
history.

## Follow-up tasks

- Execute `python -m unittest tests.test_submission_ledger -v` when a Python
  runner is available.
- For the next actual upload, populate a complete `SUBMITTED` receipt before
  uploading.
- If the exact historical cap-160 artifacts still exist, backfill their hashes
  from the files themselves; do not infer them from nearby commits.
