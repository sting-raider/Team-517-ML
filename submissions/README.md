# Submission ledger

`LEDGER.tsv` is the durable provenance record for leaderboard uploads and final
archive candidates. It stores metadata only; raw predictions, models, challenge
records, and row-level diagnostics remain outside Git.

Validate it with:

```powershell
$env:PYTHONPATH='src'
python -m ber.submission_ledger --ledger submissions/LEDGER.tsv validate
```

## Lifecycle

Use one stable `submission_id` per exact output pair.

- **GENERATED**: an output exists but has not been recorded as an uploaded
  leaderboard submission. Missing immutable hashes are allowed.
- **SUBMITTED**: the exact upload is known. This state requires UTC submission
  time, the Git code SHA, model-config SHA-256, and SHA-256 for both output
  TSVs. Do not mark a row SUBMITTED while any of those are unknown.
- **INVALIDATED**: keep the historical row, but mark it invalid if later
  provenance or validation work shows that it should not be treated as a valid
  submission.

The seeded `modal_parallel_v1_cap160` row is intentionally **GENERATED**.
Current main documents aggregate counts and calibration metrics for that export,
but not an immutable code/config/output receipt. Filling those fields from
memory would be fiction with nicer typography.

## Leaderboard feedback is not a label source

`public_score` and `private_score` are audit/history fields only. They must
never be joined back to entities, candidates, features, training labels, or
threshold-fitting data. The helper requires any row containing a leaderboard
score to use `feedback_usage=informational_only`.

Record a returned score only after the row is already `SUBMITTED`:

```powershell
python -m ber.submission_ledger --ledger submissions/LEDGER.tsv record-score \
  --submission-id <id> --public-score <score>
```

This separation matters because repeated leaderboard-driven tuning is still
feedback leakage even when nobody has a CSV column literally named
`leaderboard_label`. Humans remain extremely capable of inventing leakage
through process.

## Adding a row

Prepare one JSON object whose keys match the ledger header, then append it:

```powershell
python -m ber.submission_ledger --ledger submissions/LEDGER.tsv append \
  --row-json path/to/submission_receipt.json
```

For a `SUBMITTED` row, capture hashes from the exact artifacts that are
uploaded, not regenerated files that are believed to be equivalent. Local
metrics must name their protocol/slice in `local_protocol` and must correspond
to the same candidate/model configuration represented by the row.

Do not copy the cap-640 confirmation score into a cap-160 row. A nearby metric
from a different candidate budget is context, not evidence for the submitted
configuration.
