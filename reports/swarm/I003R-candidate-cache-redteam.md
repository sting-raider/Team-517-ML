# I003R — Red-team portable candidate cache

**Issue:** #122  
**Target:** PR #35 / `agent/i/I003-candidate-cache` @ `6dcf0f4c8705aa9446ef479dd0e2f45a567ed166`  
**Recommendation:** **FOLLOW-UP before promotion**

## Hypothesis

A stable-ID candidate cache can still create incomparable experiments if its compatibility contract does not bind the exact anchor universe or if supposedly deterministic artifacts vary across identical exports.

## Protocol

Tier-0 independent source/protocol audit of:
- `src/ber/candidate_cache.py`
- `tests/test_candidate_cache.py`
- I003 report/Issue #18/PR #35 contract

Checked export/import semantics, stable target-ID resolution, rank construction, duplicate/unknown-ID handling, cap enforcement, checksum behavior, anchor-table compatibility, portability across rowid changes, and deterministic artifact claims.

No challenge data, labels, confirmation, or frozen holdout was consumed. The local Python/container service in this chat is unavailable, so no fresh executable result is claimed.

## Positive findings

The core stable-target-ID design is sound.

- Target database rowids never enter the portable file.
- Export resolves `rid -> entity_id/source`; import resolves stable ID/source back to current rowid.
- Export prechecks unknown anchors and invalid target rowids rather than relying on inner joins that could silently drop rows.
- Final export/import row-count equality catches row multiplication/loss from duplicate database IDs.
- Duplicate candidate pairs, non-contiguous ranks, cap overflow, non-finite scores, invalid sources/hits, corrupt cache bytes, and unsafe SQL identifiers fail loudly.
- Ranking is deterministically defined at the logical row level as retrieval descending with target entity ID as the tie-break.
- The SQLite synthetic test correctly demonstrates survival across changed physical rowids.

These are meaningful improvements over sharing database-local `rid` tables.

## Findings

### Finding 1 — HIGH: cache compatibility does not bind the complete anchor universe

The manifest's `anchor_count` is computed only from anchors that appear in candidate rows. It does **not** record the full `anchor_table` row count or a stable fingerprint/list hash of the intended anchor IDs.

On import, compatibility is one-directional:
- every cached anchor must exist in the supplied `anchor_table`;
- but the supplied `anchor_table` may contain arbitrary additional anchors.

Therefore a cache produced for a subset can be imported into a superset anchor table with the same split/cap and pass all current checks. The extra anchors simply receive zero candidate rows.

Example failure class:
1. cache is exported for the 4,389 calibration anchors;
2. importer points it at a 30,000-anchor development table containing those 4,389 IDs plus others;
3. unknown-anchor check passes;
4. target checks and row count pass;
5. the resulting candidate table silently represents only the cached subset, while downstream `materialize()` can still enumerate the larger anchor table.

That is an incompatible candidate pool, not merely a metadata omission. It can alter candidate recall, oracle F0.5, training examples, and singleton behavior while the portable cache itself remains perfectly checksummed.

Zero-candidate anchors make this even more important: the cache file alone cannot distinguish "this anchor was intentionally in the universe with zero candidates" from "this anchor was never part of the experiment."

**Required fix:** bind the cache to the complete anchor universe. At minimum record:
- total rows / distinct IDs in the intended anchor table;
- a stable order-independent fingerprint of all anchor entity IDs (and ideally country/source where relevant).

Import should require exact anchor-universe identity by default, with any subset/superset use requiring an explicit mode that records the deviation.

### Finding 2 — MODERATE: the gzip artifact is not byte-deterministic despite the report's deterministic-cache claim

Export uses:

`gzip.open(temp, "wt", ...)`

Python's gzip writer uses a current-time modification timestamp when no explicit `mtime` is supplied. Consequently, two exports of identical logical candidate rows at different times can produce different compressed bytes and therefore different manifest SHA-256 values.

The CSV row ordering is deterministic, but the **artifact hash is not**.

That weakens:
- cache deduplication by SHA;
- reproducible provenance receipts;
- exact artifact comparisons across agents.

**Required fix:** write gzip with a fixed `mtime` (for example zero) using `gzip.GzipFile(..., mtime=0)` plus a text wrapper, or hash the canonical uncompressed row stream separately if compressed-byte identity is intentionally not part of the contract.

### Finding 3 — FOLLOW-UP dependency: provenance is recorded but not enforced

The manifest accepts arbitrary caller-supplied `provenance`, but:
- `validate_candidate_cache` has no `expected_provenance`/fingerprint argument;
- `import_candidate_cache` likewise validates only split/cap plus structural contents;
- the manifest itself has no independent checksum beyond the cache-byte SHA field it contains.

I003's own report explicitly defers canonical provenance population to I002, so this is not treated as an implementation regression. It is, however, a merge/integration condition before the cache is advertised as preventing stale candidate reuse across modeling experiments.

Once I002-style fingerprints are available, import should be able to require the expected blocker/data/config fingerprint rather than merely return the stored provenance for callers to remember to inspect.

## Tests missing from PR #35

The existing tests cover changed target rowids and several corruption cases, but they do not cover the most dangerous compatibility asymmetry.

Add:
1. export from anchor subset A, import into strict superset B -> reject by default;
2. zero-candidate anchor present in exported anchor universe -> its membership in the universe survives the manifest;
3. identical logical exports performed at different times -> identical canonical artifact/content fingerprint;
4. when provenance enforcement lands, wrong current provenance -> fail closed.

## Risks

- Static audit only; this chat's Python/container execution service is unavailable.
- Finding 1 follows directly from the manifest fields and import SQL and does not depend on DuckDB-specific behavior.
- Finding 2 concerns compressed-byte determinism, not logical row determinism.
- No official metric was re-evaluated.

## Recommendation

**FOLLOW-UP before promotion.**

Keep the stable-ID cache design, but do not use it as a canonical shared experiment boundary until the full anchor universe is fingerprinted and enforced. Fix gzip determinism if SHA equality is intended to mean identical logical cache content.

After those repairs, run the existing DuckDB vectorized round-trip test plus the new superset/zero-candidate tests in the normal project environment.
