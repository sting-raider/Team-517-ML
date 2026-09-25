# D002R — Red-team of exact expected-F0.5 decision kernel

## Hypothesis

The exact expected-F0.5 decoder proposed in D002 / PR #39 is mathematically and numerically correct **under its stated assumptions**: candidate labels are independent Bernoulli variables, supplied probabilities are calibrated, and the modeled candidate set contains the complete truth set.

This task is deliberate independent replication. It does not test whether those assumptions hold for the challenge pipeline.

## Target reviewed

- PR: #39, `D002: Add exact expected-F0.5 decision kernel`
- source branch: `agent/d/D002-expected-f05-kernel`
- reviewed source blob: `src/ber/decision.py` SHA `b287d92e9122b8645255a39f5881fbbeb1ea2ef2`
- reviewed test blob: `tests/test_decision.py` SHA `2f18984cada2d4b54b9efc34a44f864695dee131`

No challenge labels, confirmation anchors, or frozen holdout were consumed.

## Protocol

Three independent checks were performed in a working Python 3 runtime.

### 1. Committed unit-test reproduction

The six tests in `tests/test_decision.py` were reproduced and executed against the reviewed decoder logic:

```text
test_empty_candidate_list_scores_one ... ok
test_empty_prediction_can_beat_every_nonempty_prefix ... ok
test_exact_dp_matches_exhaustive_truth_enumeration ... ok
test_multi_match_prefix_can_beat_top_one ... ok
test_original_indices_are_returned_after_probability_sort ... ok
test_probability_validation_and_explicit_size_bound ... ok

Ran 6 tests
OK
```

### 2. Broad DP-vs-brute-force truth enumeration

An independent brute-force implementation enumerated every binary truth assignment and compared every probability-ranked prefix utility with the D002 dynamic program.

Coverage:
- all vectors of length 0 through 5 over probabilities `{0, 0.1, 0.25, 0.5, 0.75, 0.9, 1}`
- deterministic random vectors for lengths 6 through 10
- total vectors checked: **20,326**

Result:
- maximum absolute utility error: **2.8866e-15**
- ordering and every prefix utility matched within floating-point precision
- no mismatch found

### 3. Global optimum over every possible prediction subset

The D002 proof claims that, for fixed prediction size, the highest-probability prefix is sufficient. To test that independently rather than trusting the proof, an exhaustive checker evaluated **every possible prediction subset** and **every possible truth assignment**.

Coverage:
- edge families including empty, certain 0/1, tied probabilities, and documented D002 examples
- deterministic random vectors for lengths 1 through 8
- total vectors checked: **545**

Result:
- decoder-selected prefix expected utility equaled the global best subset utility in every case
- maximum global-optimum gap: **0.0**

### 4. Bound/runtime sanity

For one deterministic random 64-candidate vector:
- all 65 prefix utilities were finite and within [0,1]
- exact Python decoder runtime: **0.00749 s** in this runtime
- no numerical instability was observed

This confirms the current implementation is suitable as a bounded reference kernel. It does **not** imply that calling it for every raw 640-candidate anchor would be production-feasible.

## Mathematical audit

The implementation uses the official row score for non-empty truth:

```text
1.25 * TP / (|P| + 0.25 * |T|)
```

For a predicted prefix of size k:
- `T` = true labels inside the prefix
- `F` = true labels outside the prefix
- `|truth| = T + F`

so the implementation's

```text
1.25 * T / (k + 0.25 * (T + F))
```

is correct.

The empty prediction utility is `P(|truth|=0)`, which exactly matches the competition's special singleton convention **only under candidate completeness**.

The top-k exchange argument is also sound under independence: swapping an unselected higher-probability item for a selected lower-probability item changes only the two one-positive states; their denominators are equal because total truth cardinality is unchanged, and the expected numerator advantage is proportional to `p_high - p_low`.

The exhaustive all-subset check independently confirms this argument for the tested cases.

## Findings

### PASS: exact kernel mathematics

No denominator bug, singleton-convention bug, ordering bug, or Poisson-binomial DP bug was found.

### PASS: validation behavior

The decoder correctly:
- rejects probabilities outside [0,1], NaN, and infinity
- rejects silent truncation beyond the explicit candidate bound
- preserves stable original-index order for tied probabilities
- prefers smaller prediction sets within the configured tie tolerance
- handles an empty modeled candidate list consistently with its complete-truth assumption

### PASS: numerical behavior at n=64

The exact reference implementation was stable and fast enough for offline/reference use on a small postfiltered set.

## Critical integration risks remain unchanged

This verification **does not promote the decoder directly into the selected pipeline**.

1. **Candidate completeness is false in the measured pipeline.** Pair recall at cap 640 is 0.947246 and blocking-oracle macro F0.5 is 0.980951. The kernel's empty-set probability ignores probability mass in missed true links and therefore can be overconfident about singleton decisions.

2. **Pair labels are correlated.** Multiple Source-2/Source-3 records may match one anchor, so independent Bernoulli labels are an approximation rather than a data-generating fact.

3. **CatBoost scores are not automatically calibrated probabilities.** Exact expected utility with miscalibrated scores is exactly wrong mathematics applied very precisely, a classic human achievement.

4. **Top-N prefiltering changes the modeled truth space.** Any bounded production use must model or explicitly stress-test discarded probability/tail mass.

5. **The current selected threshold cannot be compared from this task.** A valid empirical integration needs identical anchors/candidates/scores and separate calibration/evaluation partitions.

## Leakage / integrity checks

- no challenge data consumed: PASS
- no confirmation/frozen holdout consumed: PASS
- no IDs used as evidence: PASS
- no model/threshold retuning: PASS
- independent brute-force implementation used for verification: PASS

## Recommendation

**PROMOTE AS REFERENCE KERNEL; FOLLOW-UP FOR PIPELINE INTEGRATION.**

PR #39's `decision.py` is correct enough to serve as the exact small-set oracle/reference implementation.

Do **not** promote expected-F0.5 decoding as the production decision rule until an empirical D002 follow-up:
- calibrates candidate probabilities without leakage,
- accounts for missed-match/tail probability,
- compares against the current global threshold on exactly the same anchors,
- reports official macro F0.5, singleton FPR, US/India/cardinality slices, unchanged candidate recall, and paired uncertainty.

No competition-score gain is claimed by this red-team task.
