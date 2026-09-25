# X008 — Source-1 blocker-key survivability and collision audit

## Hypothesis
The current blocker-v2 key generator may yield weaker or more collision-prone lexical evidence for India and unseen-France Source-1 anchors than for US anchors. A full Source-1 census of emitted key families and within-country fanout was intended to identify retrieval pressure before S2/S3 candidate generation.

## Change
No production model or blocker behavior was changed.

The intended analysis reproduces the exact latest-main semantics from:
- `src/ber/data.py::norm`
- `src/ber/blocking.py::address_words`
- `src/ber/blocking.py::block_keys`

Planned families were exact name/address (`n:`, `a:`), name token (`w:`), address token (`u:`), adjacent address token pair (`v:`), and numeric composites (`h:`, `z:`, `d:`).

## Protocol
Task: Issue #147, branch `agent/x/X008-block-key-survivability`.

Required raw inputs:
- complete `train_source1.tsv`
- complete `test_source1.tsv`

No sampling was permitted for final metrics.

Drive access was verified through the connected Google Drive source. The complete files were successfully transferred into the chat runtime:
- `train_source1.tsv`: 210,069,713 bytes
- `test_source1.tsv`: 175,022,086 bytes

The full S2/S3 files were also located but remain above the Drive connector's 256 MiB raw-transfer ceiling; this experiment did not require them for the Source-1 census.

Execution attempts:
1. private Python runtime: platform `ClientError` before user code executed;
2. container runtime: platform `ClientError` before shell command executed;
3. visible Python runtime: platform `ClientError` before user code executed.

These failures occurred after the S1 files were mounted. No partial sample or conversational-text substitute was used.

## Results
**BLOCKED. No aggregate census metric is claimed.**

Because no compute backend accepted execution, the planned full-population key-family/fanout statistics could not be produced. In particular, this report does **not** claim country differences in key survival, key frequency, collision burden, France robustness, candidate recall, or macro F0.5.

Static source inspection confirms only the current mechanics:
- normalization lowercases, strips accents, replaces non-letter/non-number runs with spaces;
- address token keys exclude pure numeric tokens and a fixed stop list;
- generic name/address token families are later limited to four rarest eligible keys per family using target-side posting frequency;
- postings with frequency above 1000 are suppressed by blocker v2.

Those are implementation facts, not empirical country-level findings.

## Error analysis
The failure is environmental rather than methodological:
- Drive authentication is working for sub-256 MiB raw files;
- both complete S1 files are present in the runtime;
- compute services fail before reading even the first line.

A second data-plane limitation was independently re-verified during startup: raw `train_source2.tsv` (489,301,488 bytes) is rejected by the Drive connector with HTTP 413 because it exceeds 268,435,456 bytes. This did not itself block X008, but it prevents extending X008 directly to measured target-side posting frequencies or pair recall in this chat.

## Risks
- Reporting S1-only fanout as actual S2/S3 retrieval fanout would be misleading; the planned census explicitly separated S1 proxy frequency from measured target-side frequency.
- France is unlabeled, so even a completed census would diagnose representation pressure rather than French matching quality.
- No empirical result should be inferred from the static observations above.

## Recommendation
**BLOCKED / HANDOFF.**

Recover this exact task only in a runtime where Python/DuckDB execution is healthy. The two required S1 files are below the Drive transfer limit, so no sharding is necessary. Run the complete population, preserve exact blocker semantics, and keep S1-frequency proxy language explicit.

Do not promote a blocker change from this report alone.

## Follow-up
When compute is available:
1. run the full train/test S1 census from Issue #147;
2. report per-country family coverage and S1 fanout quantiles;
3. only then create a narrower retrieval experiment if a concrete India/France failure mode appears.
