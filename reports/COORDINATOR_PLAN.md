# Coordinator decision — 25 September 2026

Public submission 1 scored **0.898**. It used blocker v2 cap 160, depth-10
CatBoost, 47 features, and threshold 0.575. Its calibration result was 0.927197;
the independent 0.928835 confirmation belongs to the different cap-640 model
configuration and is not the submitted configuration's validation score.

The user reported four submissions remaining on September 25; the current day's allowance has not been rechecked. Research
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


## September 26 integration update

INT001 completed: depth 10 scored 0.942740 on calibration and 0.938604 on the
reused development holdout, versus the deployed baseline's 0.927197 / 0.926837.
Depth 8 was weaker (0.940225 / 0.937631). These models are **not promoted**:
M002R (#165) identified ID-order dependence in the ordinal rank feature, also
present in the initial integration. INT002 regenerates all features in a new
cache directory with score-only dense rank and retrains depth 10. The feature
name changes to reject incompatible checkpoints. No INT001 model is exported.

The real-inventory character retrieval study reproduced baseline recall exactly.
At cap 160, base-plus-character rank fusion raises candidate pair recall from
0.925308 to 0.945666, oracle macro F0.5 from 0.973081 to 0.980810, and average
candidates from 142.18 to 148.05. Source-aware-plus-character fusion reaches
0.947041 recall / 0.981086 oracle at 155.50 average candidates. The latter is
slightly stronger overall but weaker in India than base-plus-character fusion;
therefore both remain candidates for the next matched-pool comparison. These
are retrieval **oracle** results, not classifier scores. See int001_retrieval.json.

Research decisions:

- M006a (#74), F004/F005 (#29/#57): integrate matched candidate pools, more
  fitting anchors, and inventory commonness features now.
- M002R (#165): integrate score-only rank before any submission.
- I020 (#168): respect the unusually high singleton fraction in the India
  development holdout; use the predeclared independent matcher confirmation.
- R020 (#87), character retrieval proposals: move to empirical full-inventory
  experiments; our measured retrieval study supplies evidence the blocked chats
  could not produce.
- D001a (#58), R009a (#129): do not use weak Source-1-only singleton/cardinality
  priors to force empty predictions or candidate budgets.
- M004 (#158): fuzzy token alignment is a useful next matcher ablation, but has
  no measured competition gain and approximately doubles its feature microbench.
- X002/X008 (#123/#156): retain accent-folded retrieval. A Unicode-preserving
  parallel view is a future ablation, not a justified wholesale normalization
  change. France remains unlabeled.
- D013 (#141): exact threshold search is calibration-only research. Do not
  consume submission slots on small, unconfirmed threshold differences.
- R022 (#112): correlated blocker evidence motivates future family-aware
  reranking; synthetic score inflation alone does not establish a real gain.
- I021 (#171): both matcher and retrieval matter. Its cap-640 error budget is
  historical context and must not be attached to the deployed cap-160 file.

The next submission is the corrected, confirmed matcher at cap 160. The next
research priority is complementary retrieval followed by retraining on that
candidate distribution, with special attention to India and smaller candidate
sets. Do not merge every research branch into production.
