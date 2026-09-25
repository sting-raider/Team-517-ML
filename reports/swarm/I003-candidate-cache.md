# I003 — Portable central candidate cache

## Hypothesis

The current blocker tables identify targets by DuckDB `rowid`. That is efficient inside one database, but `rowid` is not a portable identity: rebuilding/importing the same records in a different physical order can point the same integer at a different entity. A stable entity-ID candidate cache should let retrieval and matcher agents reuse exactly the same candidate membership while failing loudly on stale, corrupt, or incompatible artifacts.

## Change

Added `src/ber/candidate_cache.py`.

The cache is a deterministic gzip CSV with columns:

`anchor,target,retrieval,hits,source,rank`

A JSON sidecar records:
- schema version and column schema;
- split and declared candidate cap;
- row/anchor counts and maximum rank;
- SHA-256 of the compressed cache;
- caller-supplied provenance.

Export resolves database-local target `rowid` values to stable challenge `entity_id` values. Import resolves those stable IDs back to the current database's rowids, so the canonical downstream candidate table remains compatible with existing matcher code.

Validation rejects checksum/schema mismatches, non-contiguous ranks, duplicate pairs, cap overflow, invalid source/hit metadata, non-finite scores, unknown anchors, unknown/source-mismatched targets, row-count inflation/loss, and unsafe SQL identifiers.

The production DuckDB import path uses vectorized `read_csv` rather than Python row inserts. A generic `executemany` path exists only so validation and round-trip semantics can be tested without DuckDB installed.

## Protocol

Tier 0/1 infrastructure experiment; no challenge labels or F0.5 tuning involved.

Test command:

```bash
PYTHONPATH=src python -m unittest tests.test_candidate_cache -v
```

In this restricted analysis container the equivalent discovery command was:

```bash
PYTHONPATH=/mnt/data/i003/src python -m unittest discover -s /mnt/data/i003/tests -v
```

Tests use synthetic source-one/source-two/source-three records. The primary round-trip deliberately changes target insertion order between exporter and importer so physical rowids differ.

A conditional DuckDB integration test is included. It runs automatically where the repository's pinned `duckdb==1.5.5` dependency is installed; this analysis container lacks DuckDB and cannot install packages because outbound package-network access is unavailable.

A 20,000-candidate / 500-anchor / cap-40 synthetic throughput smoke test was also run through the dependency-light SQLite path.

## Results

Unit tests: **8 discovered; 7 passed; 1 skipped**. The only skip is the explicit DuckDB vectorized-path test because DuckDB is absent from this runtime.

Covered behaviors:
1. stable-ID round-trip survives changed physical rowids;
2. cache checksum corruption is rejected;
3. duplicate pair corruption is rejected even after recomputing the checksum;
4. expected-cap mismatch is rejected;
5. unknown/source-mismatched targets are rejected;
6. export refuses unknown anchors instead of silently dropping rows;
7. unsafe SQL identifiers are rejected;
8. DuckDB vectorized round-trip is present and conditionally executed when DuckDB exists.

Synthetic 20k smoke:
- rows: 20,000;
- anchors: 500;
- compressed cache: 53,514 bytes;
- export: 0.533 s (~37.5k rows/s);
- validation: 0.059 s;
- generic SQLite import: 13.033 s (~1.53k rows/s);
- restored rows/anchors: exactly 20,000 / 500.

The SQLite import timing is **not** a production throughput estimate. The committed DuckDB path avoids that Python insertion bottleneck by loading the gzip CSV in DuckDB.

No official macro F0.5 change is claimed. This task changes artifact portability and validation, not candidate generation or matching behavior.

## Error analysis

The original failure mode is concrete: candidate artifacts built around `rid`/DuckDB `rowid` are only meaningful against the exact physical database that produced them. A separately rebuilt database can assign different rowids to the same stable entity IDs.

The synthetic round-trip reproduces that condition and confirms the cache restores the same stable candidate pairs after rowids change.

Additional red-team checks found two silent-failure risks and closed them:
- joining during export could otherwise drop candidate rows with an unknown anchor/target; explicit prechecks plus final row-count equality now reject this;
- arbitrary table names interpolated into SQL could be unsafe; identifiers are now strictly validated.

## Risks

- The vectorized DuckDB import branch could not execute in this restricted container. The conditional integration test should be run in the normal project environment before relying on the cache for a large shared experiment.
- Cache provenance is intentionally caller-supplied. I002 config hashing can later populate it with a canonical config/data fingerprint; I003 does not duplicate that active task.
- Gzip CSV favors portability and auditability over maximum binary throughput. If cache size becomes material, the stable schema can later gain a Parquet representation without changing the entity-ID contract.

## Recommendation

**PROMOTE** as an independent infrastructure helper, with the normal project test suite (including the DuckDB conditional test) as the merge gate.

It does not alter blocker scores, candidate membership, matcher features, thresholds, or the official metric. Its value is making candidate reuse explicit, portable, checksummed, and comparable across parallel agents.

## Follow-up

- Integrate I002's canonical config fingerprint into the manifest provenance once I002 lands.
- Use this format for a candidate-producing experiment and verify stable pair hashes before/after cache reuse.
- Benchmark the DuckDB vectorized path on a representative real candidate cache; do not extrapolate the SQLite fallback timing.
