# I007F — Paired-bootstrap hardening after red-team

## Hypothesis

The canonical I007 paired-bootstrap utility is mathematically sound, but concrete artifact/alignment/memory-provenance gaps identified by I007R can make the tool harder to audit or unsafe on larger future evaluation slices. Fixing those gaps should preserve the statistical result while making the utility fail-loud and reviewable.

## Base / recovery

- Canonical task: I007, Issue #33, PR #41.
- Canonical branch: `agent/i/I007-paired-entity-bootstrap`.
- Red-team: I007R, Issue #117.
- This branch is stacked from the canonical I007 branch. The later duplicate Issue #111 / PR #125 was closed and is not part of this implementation.

## Exact change

`src/ber/uncertainty.py` now:
- records input counts, shared-anchor count, and baseline-only/candidate-only drops whenever explicit intersection mode is used;
- records the sign-test non-tie count and the tie policy (`discard`);
- records bootstrap method, NumPy version, bootstrap standard error, requested/effective replicate chunk size, and maximum sampled indices per allocation;
- caps sampled-index allocation with `max_draws_per_chunk`;
- if one bootstrap replicate itself is larger than the allocation cap, accumulates that replicate in multiple draw blocks instead of allocating the full index vector at once;
- exposes `--chunk-size` and `--max-draws-per-chunk` in the CLI;
- preserves strict same-anchor comparison by default.

Durable artifact fixes:
- rewrote `reports/swarm/I007-paired-bootstrap.md` with real Markdown line breaks instead of literal `\\n` escape sequences;
- rewrote the I007 registry row using real TSV separators instead of literal `\\t` sequences.

`tests/test_uncertainty.py` extends the canonical suite with regression coverage for intersection drop counts, sign-test tie-policy metadata, bounded allocation in both chunking regimes, bootstrap SE/provenance, and seeded-statistic invariance across different allocation partitions.

## Protocol

Tier 0/1 synthetic validation only. No challenge records, confirmation/frozen holdout, prediction artifact, or leaderboard feedback was consumed.

Focused test command:

```bash
PYTHONPATH=/mnt/data/i007f/src \
  python -m unittest discover -s /mnt/data/i007f/tests -v
```

Runtime environment:
- Python 3.13.5
- NumPy 2.3.5 in this ChatGPT runtime
- repository dependency pin remains NumPy 2.3.2

A separate CLI smoke used two shared synthetic anchors plus one baseline-only and one candidate-only anchor under explicit `--intersection`.

A realistic-size synthetic stress check used 5,000 anchors and the default 10,000 bootstrap iterations.

## Baseline

Canonical I007 before hardening:
- paired resampling semantics: PASS under I007R;
- exact two-sided sign test: PASS under I007R;
- strict anchor mismatch failure by default: present;
- explicit intersection mode: present;
- durable report/registry formatting: FAIL under I007R because literal escape sequences were committed;
- intersection drop-count provenance: absent;
- sign-test tie policy: implicit rather than explicit;
- bootstrap allocation: fixed replicate chunk size, so index allocation scaled as `chunk_size × entities`;
- bootstrap SE / method / NumPy-version provenance: absent.

No competition metric is a baseline for this infrastructure task.

## Results

Focused suite: **10/10 tests passed**.

Measured focused-suite resource use:
- wall time: **0.63 s**
- peak RSS: **93,480 KiB**

The CLI intersection smoke returned:
- baseline input entities: 3
- candidate input entities: 3
- shared entities: 2
- baseline-only dropped: 1
- candidate-only dropped: 1
- sign-test tie policy: `discard`
- method: `paired_entity_percentile_bootstrap`
- configured maximum draws per allocation: 7
- requested country slices were emitted for India and US

The 5,000-anchor / 10,000-iteration synthetic stress check completed with:
- wall time: **1.19 s**
- peak RSS: **114,724 KiB**
- effective replicate chunk size: 256
- configured draw-allocation cap: 2,000,000 sampled indices
- bootstrap SE: 2.8310e-05 for the synthetic delta construction
- 95% paired delta interval: approximately [-5.7005e-05, 5.4200e-05]

No competition F0.5 delta is claimed.

## Red-team closure

### Durable artifacts
**FIXED.** The canonical Markdown report now contains actual line breaks. The registry is rewritten as a parseable TSV with real tab delimiters and line endings.

### Intersection accounting
**FIXED.** Intersection mode now discloses the two input sizes, shared size, and the count dropped from each side. Strict mode remains the default.

### Sign-test ties
**FIXED / EXPLICIT.** Exact ties are discarded from the binomial sign test, `sign_test_non_ties` is reported, and the output names the tie policy.

### Memory scaling
**FIXED.** The RNG never intentionally allocates an index matrix larger than the configured draw cap. If a single replicate exceeds that cap, it is sampled in blocks. A regression test verifies that partitioning the same seeded random stream changes allocation shape but not the resulting bootstrap statistics.

### Provenance
**IMPROVED.** Results now include method identifier, NumPy version, bootstrap SE, requested/effective chunk sizes, seed, iteration count, confidence, and draw cap.

## Error analysis

The critical I007R finding was not a statistical error in the paired bootstrap. It was a durable-artifact defect: a report and registry entry that visually encoded escape sequences rather than using the file formats they claimed to be. That is dangerous because automated registry tooling can treat the entire experiment row as one column.

Intersection mode is another sharp edge. Even when explicitly requested, a result without drop counts can hide a material population change. The new alignment block makes that loss visible in every overall result.

The original fixed `chunk_size=256` is harmless at the current 4k–5k diagnostic scale, but it scales poorly if a future fixed slice becomes much larger. The draw cap removes that avoidable allocation cliff without changing the statistical unit.

## Risks

- The exact sign test still uses Python integer binomial coefficients. It is fast at the team's current 4k–5k evaluation scale; very large non-tie counts should be profiled before using it on million-anchor comparisons.
- Percentile bootstrap uncertainty only describes entity-sampling variation inside the evaluated population. It does not repair stale caches, repeated holdout tuning, country shift, or protocol mismatch.
- `bootstrap_probability_delta_gt_0` remains a descriptive bootstrap fraction, not a Bayesian posterior probability or a calibrated p-value.
- NumPy-version provenance makes RNG context visible; it does not promise identical random streams across all future NumPy versions.

## Recommendation

**PROMOTE** the I007F hardening and use it as the merge-ready form of canonical I007. The core I007 statistical conclusion is unchanged; the follow-up closes the red-team's durable-artifact blocker and makes deliberate intersection / memory behavior auditable.

No retrieval, matcher, threshold, candidate, or submission behavior changes.
