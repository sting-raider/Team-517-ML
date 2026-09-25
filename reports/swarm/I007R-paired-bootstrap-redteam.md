# I007R — Red-team paired entity-bootstrap utility

**Issue:** #117  
**Target:** PR #41 / `agent/i/I007-paired-entity-bootstrap` @ `349ab748506dd1a3e472ab832aa3f8bd04a227b8`  
**Recommendation:** **FOLLOW-UP, then PROMOTE**

## Hypothesis

The paired bootstrap/sign-test utility could contain statistical or alignment behavior that makes tiny macro-F0.5 deltas appear more robust than they are.

## Protocol

Tier-0 independent source/mathematical audit of:
- `src/ber/uncertainty.py`
- `tests/test_uncertainty.py`
- `reports/swarm/I007-paired-bootstrap.md`
- `experiments/REGISTRY.tsv`
- original I007 issue #33 and PR #41 contract

No challenge data, confirmation, frozen holdout, or leaderboard evidence was consumed. The local Python/container service in this chat is unavailable, so this report does not claim a fresh executable test run.

## Statistical kernel audit

The core method is correct for its stated purpose.

### Pairing

`align_scores()` converts both inputs to anchor->score mappings, rejects duplicate anchors, rejects non-finite/out-of-range scores, and requires identical anchor universes unless explicit intersection mode is requested.

`paired_bootstrap()` computes `delta = candidate - baseline` once and resamples the same entity indices for the paired delta. This preserves the covariance of two systems evaluated on identical anchors. It does not make the common mistake of bootstrapping the systems independently.

### Bootstrap interval

The reported interval is the ordinary percentile bootstrap interval over the mean paired delta. At the current 4k–5k evaluation scale this is a reasonable diagnostic for sampling fragility. The report correctly states that it does not cover model-selection reuse, country shift, stale caches, or private-test shift.

### Exact sign test

For `wins + losses = n` and `k = min(wins, losses)`, the implementation computes:

`min(1, 2 * sum(C(n,i), i=0..k) / 2^n)`

For the symmetric Binomial(n, 0.5) null this is the exact conventional two-sided tail probability. Ties are excluded from `n`, which is correct for a sign test.

### Determinism / memory

A seeded NumPy generator is used. Bootstrap allocations are chunked over replicates. With the default chunk size 256 and ~5,000 anchors, the temporary integer-index array is about 10 MiB; at 30,000 anchors it is about 59 MiB. That is acceptable for the intended fixed-slice use, though not for multi-million-anchor full-corpus bootstraps.

## Findings

### Finding 1 — BLOCKING artifact-contract defect: required report and registry records are malformed

The committed Markdown report is not actually line-oriented Markdown:

- actual newline characters: **0**
- literal backslash-n sequences: **76**

The committed registry file has a valid header, but the I007 row is encoded with literal escape text:

- actual tab characters: **14** (the header)
- literal backslash-t sequences: **14** (the I007 row)
- actual newline characters: **1** (after the header)
- literal backslash-n sequences: **1** (the I007 row terminator)

Thus the I007 experiment row is not a valid TSV row and the report renders as one physical line containing escape sequences. This violates the swarm's durable experiment-record contract even though the Python utility itself is sound.

**Required fix:** rewrite the report with real newlines and the registry row with real tab/newline delimiters before merging.

### Finding 2 — MODERATE guardrail gap: intersection mode does not quantify discarded anchors

Intersection mode is explicitly opt-in, which is good. However the output only records:
- `entities` after intersection
- `intersection_mode: true`

It does not report the original baseline count, candidate count, number missing from candidate, or number missing from baseline.

A comparison of 100 shared anchors drawn from two very different 5,000-anchor universes can therefore produce an apparently clean aggregate report with `entities=100` and no machine-readable indication that thousands of anchors were dropped.

Because I007 is explicitly a guardrail against invalid tiny-delta comparisons, intersection mode should emit the discarded-universe counts even when the user intentionally enables it.

### Finding 3 — MODERATE sign-test sensitivity: exact floating equality defines ties

Wins/losses are counted with exact comparisons:

- `delta > 0`
- `delta < 0`

That is safe when both inputs are generated from exactly the same full-precision official `row_score` implementation and serialization. But if one pipeline rounds scores differently or reconstructs mathematically equal values with tiny floating differences, the magnitude-weighted mean delta may remain effectively zero while the sign test can report thousands of artificial wins or losses.

For a utility designed specifically to police tiny gains, the safer contract is either:
1. require exact full-precision official per-anchor scores and validate/document that invariant; or
2. expose a small `tie_tolerance` for the sign diagnostic while leaving the bootstrap mean untouched.

This is not a flaw in the bootstrap estimator itself.

## Secondary observations

- Slice metadata mismatches on shared anchors fail in the CLI before comparison.
- Missing metadata represented as `None` is silently omitted by the library slice helper; CLI TSV empty strings become explicit slice values. If the library API becomes widely used, reporting missing-slice counts would improve auditability.
- The original issue #33 did not require bootstrap standard error, so its absence is not a failure of PR #41. The newer duplicate issue #111 does request standard error and should be treated as follow-up/replication rather than evidence that I007 was never implemented.

## Risks

- Static audit only because this chat's Python/container runtime is unavailable.
- No fresh timing measurement is claimed.
- No competition metric changed.
- No challenge rows, predictions, or private diagnostics are committed.

## Recommendation

**FOLLOW-UP, then PROMOTE.**

The statistical kernel is suitable as evaluation infrastructure after repairing the malformed report/registry artifacts. The two guardrail improvements are small and worthwhile:
- emit intersection drop counts;
- define a robust tie policy for the sign test.

No reason was found to reject the paired-bootstrap approach or its core implementation.
