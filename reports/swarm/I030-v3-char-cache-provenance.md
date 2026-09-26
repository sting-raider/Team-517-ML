# I030 — Fingerprint INT003 character-index caches against stale reuse

## Hypothesis

INT003's persisted name-character retrieval index was reused based only on table existence. A deterministic cache identity covering the source inventory and behavior-defining retrieval semantics should prevent stale/partial indexes from contaminating retrieval comparisons without changing valid-cache candidate behavior.

## Change

Recovered and audited the abandoned I030 branch rather than restarting it.

The branch now:

- adds deterministic canonical hashing and relation/file signature helpers in `src/ber/provenance.py`;
- fingerprints the character-index identity from split, index version, DF cutoff, exact gram-macro SQL, the full relevant relation signature, the implementation source hash, and the DuckDB engine version;
- persists the identity/fingerprint beside each character index;
- reuses an index only when both required tables exist and the stored fingerprint exactly matches the current identity;
- rebuilds unsigned, stale, or partial caches;
- invalidates the old trust marker **before** mutating cache tables, so an interrupted partial rebuild cannot leave a mixed cache trusted by a still-matching signature;
- upgrades `modal_v3.prepare_database()` provenance from source-byte/version checks to source file signature + retrieval implementation identity and records the resulting train/test character-index fingerprints.

No blocker weights, RRF weights, candidate cap, matcher feature values, threshold, labels, or prediction rules were changed.

## Protocol

- Repository baseline: latest `main` at recovery time, merge base `f08c041b274e58ae900620ac714ec8a0a06f09b0`.
- Recovered branch: `agent/i/I030-v3-char-cache-provenance`.
- No challenge rows, labels, confirmation/frozen windows, or leaderboard feedback were read for this task.
- Static audit compared latest-main table-existence reuse with the recovered branch.
- Focused dependency-light execution used mocked relation/cache connections matching the branch's cache identity/rebuild contract.
- An explicit interrupted-rebuild test raises while replacing `train_char_index` after a partial-cache rebuild has begun.
- Runtime environment does not have DuckDB installed and cannot reach package indexes; therefore no full DuckDB integration test or full repository test collection was claimed.

## Baseline

Latest main `build_char_index()` checks only whether `<split>_char_index` exists. If it exists, the function prints a reuse message and returns. It does not prove that:

- `<split>_char_freq` is present and paired with the index;
- the source inventory is unchanged;
- the gram construction or DF cutoff is unchanged;
- the retrieval implementation is unchanged;
- the SQL/hash engine semantics are unchanged.

The prepared-v3 database receipt similarly relied on a coarse source-byte/version contract.

## Results

Focused cache-provenance tests: **5/5 PASS** in **0.002 s** in the isolated harness.

Covered behaviors:

1. identity is deterministic and changes when relation content changes;
2. a complete signed compatible cache is reused without rebuilding;
3. unsigned or mismatched caches rebuild and are re-signed;
4. a partial cache rebuilds even if the old signature matches;
5. an interrupted partial rebuild clears the signature before mutable cache work, so the next run cannot trust the mixed state.

The recovery audit found and fixed two gaps in the abandoned implementation:

- **Interrupted partial rebuild:** the old matching signature was originally deleted only after new cache tables were built. If a matching-but-partial cache triggered a rebuild and the process died after replacing only one table, a later run could see both table names plus the still-valid old signature and reuse inconsistent tables. The signature is now invalidated before cache mutation and restored only after successful completion.
- **Engine semantics:** the identity used DuckDB `hash()`/list/string behavior but did not bind the DuckDB version. The engine version is now part of the identity.

No official macro F0.5, recall, singleton, or country metric changed or was re-measured, because this is a fail-safe provenance patch and valid-cache behavior is intentionally unchanged.

## Error analysis

The important failure classes are state/provenance failures rather than model errors:

- **legacy unsigned cache:** forced rebuild;
- **semantic/config drift:** fingerprint mismatch forces rebuild;
- **source inventory drift:** relation fingerprint mismatch forces rebuild;
- **partial table state:** required-table set mismatch forces rebuild;
- **interrupted rebuild:** trust marker is already absent, so the next process rebuilds;
- **DuckDB upgrade:** engine-version mismatch forces rebuild.

The implementation is deliberately conservative. Hashing the complete `retrieval_v3.py` source file means unrelated edits in that module can also trigger a rebuild. That is extra compute, not a correctness risk.

## Risks

- The relation signature uses DuckDB aggregate hashes rather than a cryptographic full-row digest. It is intended as a deterministic stale-cache guard, not adversarial tamper detection.
- No live full-inventory DuckDB rebuild was run in this recovery environment. The branch's SQL path should receive one ordinary Modal/prepared-database run before coordinator merge if compute is convenient.
- Cache rebuild cost can increase after harmless code/engine changes because the identity is intentionally fail-closed.

## Recommendation

**PROMOTE** the integrity patch after normal review. It should not change any valid INT003 candidate set, but it removes a credible mechanism for stale/partial character-index reuse to create invalid retrieval comparisons.

## Follow-up

At the next normal INT003/character-retrieval Modal run, record one log/receipt showing:

- compatible signed cache reuse on an unchanged rerun; and
- deterministic rebuild after intentionally changing a behavior-bound identity field in a disposable database.

No new modeling experiment is required for this patch.
