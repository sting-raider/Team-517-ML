# I001R — Red-team fixed-slice benchmark semantics

**Issue:** #131  
**Target:** PR #24 / `agent/i/I001-fast-benchmark` @ `117b10f731fd32e368b95da5ab85724020bd0d44`  
**Recommendation:** **FOLLOW-UP / do not promote current head**

## Hypothesis

A canonical fixed-slice benchmark can still create false experiment comparability if the committed command is not executable or if malformed candidate/truth relations are silently normalized during scoring.

## Protocol

Tier-0 independent source/protocol audit of the exact PR #24 head, cross-checked against main:
- `src/ber/benchmark.py`
- `tests/test_benchmark.py`
- `src/ber/metrics.py`
- `src/ber/blocking.py`
- `src/ber/experiment.py`
- `src/ber/retrieval_study.py`
- I001 report and issue contract

No challenge labels beyond previously documented aggregate context were consumed in this red-team. No confirmation or frozen holdout was evaluated. Local Python/container execution is unavailable in this chat, so no fresh runtime result is claimed.

## Positive findings

Ignoring the committed syntax defect described below, the intended benchmark semantics are largely aligned with the established protocol:

- the first 30,000 Source-1 anchors are selected by `md5('sample517:' || entity_id)`;
- `fold517:<entity_id>` SHA-256 assignment matches `ber.experiment.fold`;
- calibration is the default and development holdout requires an explicit override;
- the benchmark calls the repository blocker and official `metrics.evaluate` rather than reimplementing oracle formulas;
- candidate-count quantiles use the same linear interpolation convention as NumPy's default;
- country slices preserve the same anchor-level official metric;
- target-source slices restrict truth/candidates consistently by target source;
- the separate confirmation sample is not part of the command.

These are the right design choices for a shared retrieval benchmark.

## Findings

### Finding 1 — BLOCKING: exact committed `benchmark.py` is syntactically invalid

The exact PR #24 head contains this source text around the selection hash:

```python
selection_sha256 = hashlib.sha256(('
'.join(sorted(selected)) + '
').encode()).hexdigest()
```

Inspection of the fetched file confirms:
- those are **actual newline characters** inside the single-quoted string literal;
- there are **zero literal `\n` escape sequences** in the file.

A normal single-quoted Python string cannot contain an unescaped physical newline. Therefore importing `ber.benchmark` from this exact committed head raises a syntax error before any test or benchmark code can run.

This also means the PR's reported "5/5 tests pass" evidence was necessarily produced from a different local representation/revision than the exact current GitHub source, even if the intended logic was the same.

**Required fix:** commit the intended escaped expression, then rerun the tests against the exact pushed SHA and record that SHA in the report.

### Finding 2 — HIGH: invalid candidate rowids can be silently dropped before metrics

`summarize()` loads candidates with:

```sql
SELECT p.anchor,r.entity_id,r.source
FROM candidate_table p
JOIN train r ON p.rid=r.rowid
```

An invalid/stale `rid` simply fails the inner join and disappears. There is no precheck comparing:
- raw candidate row count;
- joined row count;
- count of unknown target rowids.

A stale or malformed experiment candidate table can therefore look like a legitimate lower-recall candidate set instead of failing loudly.

For a canonical swarm benchmark, silent normalization is dangerous because it converts artifact corruption into an apparently scientific metric delta.

**Required fix:** assert every candidate row resolves to a valid Source-2/3 target before scoring and report raw/joined counts.

### Finding 3 — HIGH: duplicate candidate pairs are silently deduplicated

Candidates are accumulated into Python sets:

`candidates[anchor].add(target)`

If a candidate-producing experiment emits duplicate anchor-target rows, the benchmark silently collapses them. Candidate-count statistics are then computed from the deduplicated sets, not the raw relation.

This hides:
- duplicate-generation bugs;
- effective cap overruns;
- row-count/cost inflation;
- mismatches between reported candidate budget and actual generated comparisons.

The blocker-v2 baseline is expected to be unique, but a shared benchmark exists precisely to make experimental candidate tables comparable.

**Required fix:** explicitly test/count duplicate `(anchor,target)` pairs and reject them by default. If raw comparison cost is a desired diagnostic, report raw candidate rows separately from distinct candidate pairs.

### Finding 4 — MODERATE: missing truth rows can silently shrink the scored anchor universe

Benchmark anchors are joined to truth using an inner join:

```sql
SELECT a.entity_id,a.country,g.matches
FROM benchmark_anchors a JOIN truth g ON a.entity_id=g.anchor
```

If the prepared truth table is stale/corrupt and misses an anchor, that anchor disappears from `truth` and from all metrics. The top-level report still records `anchors_selected` from the pre-join selection, so a careful human could notice a discrepancy, but the command does not fail.

Current dataset audits show truth completeness, so this is not evidence that the recorded baseline is wrong. It is a fail-loudness gap in the benchmark guard.

**Required fix:** assert one-and-only-one truth row for every selected anchor before metric computation.

## Provenance interaction

I001 currently records:
- selection SHA;
- candidate cap;
- retrieval index integer version;
- runtime.

Its own report already recognizes that the version integer does not prove current data/index identity and hands that problem to I002. I001R agrees. Once I002 is repaired, the benchmark should record the actual signed index/blocker/data fingerprint rather than only version `2`.

## Risks

- Static audit only because local Python/container execution is unavailable.
- Finding 1 is a direct source-grammar defect in the exact GitHub head.
- Findings 2–4 describe malformed/stale relation behavior; the current audited challenge database was previously reported clean.
- No competition metric was changed or re-measured.

## Recommendation

**FOLLOW-UP / do not promote current PR head.**

Repair the committed newline escaping first and rerun the test suite against the exact pushed SHA. Then add fail-loud checks for unresolved target rowids, duplicate pairs, and truth-universe completeness before making I001 the canonical benchmark command.

After those fixes, run the already-planned full blocker smoke and require exact reproduction of the stored calibration cap-640 metrics on the same selection SHA.
