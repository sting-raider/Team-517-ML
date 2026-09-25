# Coordinator decision — 25 September 2026

Public submission 1 scored **0.898**. It used blocker v2 cap 160, depth-10
CatBoost, 47 features, and threshold 0.575. Its calibration result was 0.927197;
the independent 0.928835 confirmation belongs to the different cap-640 model
configuration and is not the submitted configuration's validation score.

Four daily submissions remain at the start of this integration cycle. Research
branches are evidence and prototypes, not promoted production implementations.

## INT001: larger matched-pool matcher

The M006a audit (#74) identifies a real cap-80 fitting versus cap-160 inference
distribution mismatch. F004 (#29) and F005 (#57) motivate frequency-aware evidence
for common names and shared addresses. We therefore train on cap-160 retrieved
pairs, add four inventory-frequency and two within-candidate rank features, and
increase fitting from roughly 18k to roughly 108k anchors. No positives are
injected into candidates. Compare depth 8 and 10 on Modal L4 GPUs.

The existing first-30k development population retains its original fold roles.
Additional fitting anchors come only from the fit fold at hash positions
50,001–200,000. Positions 30,001–50,000 are excluded from fitting. A selected
configuration is checked at positions 40,001–45,000, once, without recalibration.
This sample is held out from this matcher's fitting/selection; full-S1 research
audits have inspected labels across the dataset, so it is not called globally
untouched by every swarm activity.

## Retrieval experiment in parallel

R020 (#87) motivates source-specific frequency cutoffs; character-name retrieval
is a complementary spelling-tolerant channel absent from blocker v2. Evaluate
them against the complete target inventory on the exact calibration anchors.
Reproduce the existing cap-160 recall before accepting comparisons. Report raw
union and fixed-cap results; larger candidate lists alone are not a free gain.

The current cap-160 calibration oracle is 0.973081. Reaching 0.998 requires better
retrieval as well as better matching. No prediction that the current changes will
reach 0.998 is made.

## Submission gates

Promote measured improvements with acceptable country/singleton behavior and a
documented candidate budget. Preserve the first file. Use later slots for a
retrieval improvement or complementary ensemble only if local evidence supports
them. Do not submit four arbitrary threshold variants merely to use the allowance.

Do not pursue Source-1-only singleton gating: D001a (#58) found chance-level
ranking. Expected-F0.5 decoding remains exploratory until probabilities and
missing-candidate assumptions are validated on real retrieved pairs.
