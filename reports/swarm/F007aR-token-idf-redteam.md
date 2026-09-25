# F007aR — Red-team Source-1 token-DF blocker-proxy semantics

## Hypothesis
F007a / PR #155 contains useful India-specific Source-1 evidence, but its strongest address-probe number may be easy to misread as measured production blocker behavior even though production blocker eligibility/ranking is determined by S2/S3 target posting frequencies.

## Change
No production code, model, retrieval configuration, challenge data, or F007a implementation was changed.

This is an independent static source/report/test audit of:
- PR #155 / Issue #106;
- `src/ber/token_idf_audit.py` on `agent/r/F007a-s1-token-idf-audit`;
- `tests/test_token_idf_audit.py`;
- latest-main `src/ber/blocking.py`;
- latest-main `src/ber/data.py`.

## Protocol
No confirmation/frozen holdout, leaderboard feedback, raw challenge rows, or external identity data were consumed.

The audit compared each F007a statistic/label against the exact production definitions that matter for query-key eligibility and ranking.

Production blocker-v2:
1. builds `train_freq` from **Source 2 + Source 3 target records**;
2. hashes by country + key but does **not** separate S2 from S3 in the frequency table;
3. removes target postings with pooled target frequency >1000;
4. for an S1 query, joins query keys to that target-side frequency table;
5. retains at most the four lowest-target-frequency keys per token-like family.

F007a:
1. scans **Source 1 only**;
2. computes country-local Source-1 document frequency;
3. treats Source-1 DF<=1000 as a proxy for target eligibility;
4. orders/selects the four lowest-Source-1-DF direct word keys.

## Results

### 1. Core Source-1 census is internally coherent and explicitly scoped in the PR body
The PR body correctly says:

> “under Source-1 DF as a target-side proxy”

and explicitly says the experiment does not establish a recall/F0.5 gain.

The helper uses a set of tokens per row, so its Source-1 counters are document frequencies rather than raw token-occurrence counts. That is the correct Source-1 analogue of the production index's one-key-per-record behavior after `block_keys(...)` is deduplicated.

The reported arithmetic for the headline proxy is consistent with the reported numerator/denominator:
- US proxy dropped keys: 205 / 1,672,031 = about 0.0123%;
- India proxy dropped keys: 170,917 / 2,274,335 = about 7.515%.

No arithmetic contradiction was found in the report itself.

### 2. The 7.515% number is **not** measured production blocker truncation
This is the most important semantic finding.

Production `query_keys` uses `train_freq`, whose frequencies come from the pooled S2/S3 target inventory. F007a uses Source-1 country-local DF for both:
- the <=1000 eligibility decision; and
- the ordering that decides which four keys survive.

Therefore the exact set of “eligible” words and the exact set of four selected words can differ from production even for the same anchor. Source multiplicity and corruption can make target posting frequency materially different from Source-1 document frequency.

Safe interpretation:

**F007a measures an India-heavy Source-1 lexical-richness / S1-DF proxy asymmetry that motivates a target-side experiment.**

Unsafe interpretation:

**The current production blocker is known to discard 7.515% of India's eligible address-word query keys.**

The PR body mostly uses the safe wording. The longer report occasionally crosses into the stronger wording, for example calling the proxy result “the current four-rarest address-word probe limit” after the DF<=1000 filter.

### 3. One table label mixes pre-cutoff lexical eligibility with DF eligibility
`raw_token_count_gt_probe` is incremented when:

```python
if len(toks) > max_probes:
    acc["raw_token_count_gt_probe"] += 1
```

This happens **before** filtering to `df[x] <= 1000`.

The report labels this row “Anchors with >4 eligible address words”. That can be read as “>4 DF<=1000 words”, but the implementation actually means “>4 words that pass lexical length/stopword/numeric rules before the DF cutoff”.

This does not change the separately reported `dropped_by_probe_limit` calculation, which does filter to DF<=1000 first. The label should be tightened to avoid combining two different notions of eligibility.

### 4. Numeric-channel parity is approximate, not exact
Production numeric extraction uses ASCII regex `[0-9]+`.

F007a uses Python `\d+` and `str.isdigit()`, which recognize a broader Unicode digit class. Production normalization is DuckDB `strip_accents`; F007a uses Python NFD + combining-mark removal.

The report already acknowledges normalization approximation and reports only 554 non-ASCII Source-1 addresses, all India. This makes the discrepancy unlikely to explain the large US/India proxy gap, but the digit-coverage number should still be described as a close proxy rather than exact production-channel coverage.

### 5. The documented reproduction command does not reproduce the measured execution protocol
Committed `audit()` performs:
- one full-file DF/structure scan covering all countries;
- one full-file coverage scan covering all countries.

That is two complete Source-1 scans.

The report says the empirical result/runtime was produced as:
- US DF census;
- India DF census;
- US coverage;
- India coverage;

for **four deterministic streaming scans**, with four separate measured runtimes totaling ~154.5 seconds.

No committed four-pass country-specific execution path or commands are provided. The documented reproduction command invokes the two-pass `audit()` implementation.

The aggregate mathematics should be equivalent if the uncommitted country-specific procedure used the same functions and filtering, but that equivalence is currently asserted rather than reproducibly demonstrated. The reported runtime definitely does not correspond to the documented command.

### 6. Tests protect basic behavior but not the headline semantics
The two tests verify:
- country partitioning;
- normalization on one accented example;
- stopword/numeric exclusion;
- that probe truncation can occur;
- digit coverage on a tiny case.

They do **not** independently assert:
- the exact DF<=1000 then top-k ordering contract;
- a known dropped-key numerator/denominator;
- parity with target-side production frequency semantics;
- the two-pass reproduction path versus the four-pass measured path.

The tests are useful smoke tests, not an independent validation of the 7.515% headline.

## Error analysis
Three classes of issue were found:

1. **Proxy-to-production interpretation risk**: large and scientifically important. S1 DF cannot establish target-side eligibility/order.
2. **Label/protocol precision**: moderate. One table label conflates lexical eligibility with DF eligibility; runtime protocol and reproduction command differ.
3. **Unicode/numeric approximation**: small for this population based on the report's 554 non-ASCII-address count, but still not exact production parity.

No evidence was found that the Source-1 census was label-leaked, ID-leaked, or arithmetically fabricated.

## Interpretation
F007a remains useful forensic evidence.

The strongest defensible conclusion is not “India loses 7.515% of production address probes.” It is:

**Indian Source-1 addresses contain much richer low-S1-DF lexical structure under the audit's proxy, while name rare-token opportunity and address-digit coverage are weaker; this makes a target-side fixed-cap address-probe-budget ablation unusually well motivated for India.**

That hypothesis is exactly what the next full-data experiment should test.

When that experiment is run, it must use the existing pooled S2+S3 target frequency semantics unless changing those semantics is itself the experimental variable. Using source-specific target DF would confound this probe-budget question with R020a's separate source-frequency hypothesis.

## Risks
- This red-team did not rerun F007a because the current chat compute backend is unavailable.
- No committed aggregate JSON exists in PR #155, so the exact report numbers cannot be independently recomputed from an intermediate artifact without rerunning the helper.
- A target-side experiment remains blocked in this chat by the >256 MiB Drive transfer ceiling for S2/S3.

## Recommendation
**FOLLOW-UP / CLARIFY BEFORE USING AS PRODUCTION EVIDENCE.**

PR #155's high-level conclusion is worth retaining, but the report should:
1. consistently prefix the 7.515% result as an **S1-DF proxy**;
2. rename “>4 eligible address words” to indicate it is pre-DF lexical eligibility;
3. document or reproduce the actual four-pass measured procedure, or report runtime from the committed two-pass command;
4. optionally add a tiny exact test for DF cutoff + top-k dropped-key accounting.

The target-side 4-vs-6/8/adaptive fixed-cap ablation remains the correct next scientific test.

## Follow-up tasks
No new modeling direction is created by this red-team. It sharpens the existing F007a follow-up and prevents it from being conflated with measured blocker recall.
