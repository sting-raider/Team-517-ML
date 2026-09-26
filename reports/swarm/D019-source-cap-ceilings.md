# D019 — source-specific S2/S3 hard-cap F0.5 ceilings

## Hypothesis

D006a established that true S2/S3 multiplicities vary by entity, while D018 showed that a universal global output cap of 5 is already too restrictive for a 0.998 macro-F0.5 ceiling. This follow-up asks whether splitting a fixed total output budget into separate S2 and S3 hard caps is a safer precision control.

## Exact change

No production code, retrieval, matcher, threshold, or submission output is changed.

A deterministic full-population helper parses the supplied ground-truth target prefixes into per-anchor S2 and S3 counts and computes optimistic official macro-F0.5 ceilings under:

- one global perfect-ranking cap K;
- independent perfect-ranking caps (K2, K3), with the same total budget K2 + K3;
- all source-cap pairs from 0 through 6 per source;
- overall, US, and India slices.

The calculation assumes every retained link is true, so these are upper bounds. Any real decoder with ranking/calibration error can only do worse.

## Protocol

Complete supplied labeled training population, no sampling:

- train_source1.tsv: 2,206,821 rows; SHA256 591af0e1dfeb65cab71ea6ee8cb69df00f92d6ba6fa79e05746c938775d14973
- train_ground_truth.tsv: 2,206,821 rows; SHA256 70bc1d8a16c667e0155c2105d0ab2ebe41d7e7a85d8a529e3ca81c6c3a5af037

Ground-truth IDs are used only to identify their supplied source prefix S2 or S3 and to join Source-1 country. No ID value is a predictive feature.

No S2/S3 business text, candidate probabilities, model outputs, confirmation/frozen holdouts, France labels, leaderboard feedback, or external data were used.

Execution:

    python tools/experiments/d019_source_cap_ceilings.py \
      --source1 /mnt/data/train_source1.tsv \
      --truth /mnt/data/train_ground_truth.tsv \
      --out /mnt/data/d019.json \
      --max-source-cap 6

Measured runtime: 14.04 s wall time, 630,648 KiB peak RSS.

Focused tests: 5/5 PASS. One first-pass synthetic expectation was deliberately left red, diagnosed, and corrected before checkpointing: with truth (2 S2, 2 S3), caps 1+1 and 2+0 both retain two true links, so they tie. The corrected test uses a source-asymmetric truth set and now checks the intended behavior.

## Mathematical dominance check

For every anchor and non-negative source caps a and b:

min(S2, a) + min(S3, b) <= min(S2 + S3, a + b).

Because the perfect-ranking F0.5 row score is monotone in retained true positives when false positives are zero, independent source caps can never beat a global cap with the same total budget. The full-data experiment therefore measures how much ceiling is lost by imposing the extra source constraint.

The helper asserts this invariant for every evaluated source-cap pair.

## Results

| Total output budget | Global-cap ceiling | Best S2/S3 split | Best source-cap ceiling | Gap vs global | Anchors truncated by source cap |
|---:|---:|---:|---:|---:|---:|
| 4 | 0.980628 | 2 + 2 | 0.965255 | -0.015374 | 41.09% |
| 5 | 0.993766 | 2 + 3 | 0.980544 | -0.013222 | 28.04% |
| 6 | 0.998332 | 3 + 3 | 0.992632 | -0.005700 | 14.23% |
| 7 | 0.999641 | 3 + 4 | 0.996255 | -0.003386 | 8.10% |
| 8 | 0.999941 | 4 + 4 | 0.998986 | -0.000955 | 2.81% |

D018 showed that a global cap of 6 barely clears the team's aspirational 0.998 ceiling on the labeled population. Splitting that same budget into 3 S2 + 3 S3 destroys that property: the optimistic ceiling falls to 0.992632.

Under independent source caps, the first total budget whose best split clears 0.998 is 8, via 4 + 4, at 0.998986. Budget 7's best 3 + 4 split reaches only 0.996255.

The best split is mildly S3-heavy at odd budgets (2+3 for budget 5; 3+4 for budget 7), but the main result is not this small asymmetry. The dominant effect is the loss from reserving capacity separately for each source instead of letting the anchor use its total budget where its true matches actually occur.

Country checks are stable:

- US: best budget-6 split 3+3 = 0.992651; best budget-8 split 4+4 = 0.998988.
- India: best budget-6 split 3+3 = 0.992603; best budget-8 split 4+4 = 0.998982.

The conclusion is therefore not driven by one labeled country.

## Error analysis and interpretation

A per-source hard cap encodes a strong cardinality prior: unused capacity on one source cannot be transferred to the other. That is precisely the wrong behavior for anchors whose true multiplicity is source-asymmetric.

This does not invalidate source-specific score thresholds, calibration, or source-aware features. Those mechanisms can prefer higher-quality evidence from one source without mechanically preventing the other source from using additional slots when warranted.

It also does not imply that global cap 6 should be deployed. All ceilings here assume perfect ranking and zero false positives. They only identify constraints that are mathematically too restrictive before real model error is considered.

## Red-team checks

- Exact official row-score algebra is used.
- The source-cap <= same-budget global-cap dominance invariant is asserted programmatically.
- 5/5 focused tests pass after correcting one intentionally surfaced bad synthetic assumption.
- Unknown target-source prefixes fail loud.
- Duplicate/misaligned Source-1/truth anchors fail loud.
- Full-population US/India behavior is nearly identical.
- No confirmation/frozen holdout or France labels were consumed.

## Recommendation

**REJECT independent S2/S3 hard caps as a generic decision policy.**

Do not implement "cap each source at 3" merely because a total cap near 6 looks plausible. On the complete labeled population, 3+3 has a perfect-ranking ceiling of only 0.992632.

Source-aware decision work should instead use probabilities, margins, provenance, and cross-source evidence while allowing capacity to move between S2 and S3. D004-style source-specific thresholds remain scientifically distinct and worth testing once the current private candidate-probability artifacts are available.
