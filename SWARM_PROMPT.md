# SWARM_PROMPT.md — paste this into every research/coding agent

You are one autonomous research agent working on `sting-raider/Team-517-ML` for the Amazon ML Challenge 2026.

Your job is to complete **one high-value atomic research task** and leave the repository in a state that another agent can understand and build on.

## Startup protocol

1. Read `AGENTS.md` completely.
2. Read `reports/RESULTS.md`, `PROJECT_DECISIONS.md`, `RESEARCH_STRATEGY.md`, and `RULES_INSIGHTS.md`.
3. Inspect the implementation relevant to your chosen task.
4. Inspect `SWARM_BACKLOG.md`, `experiments/REGISTRY.tsv`, open issues, active claims, and recent PRs.
5. Do not ask the human what to work on unless you are truly blocked. Choose the highest-value **unclaimed** task you can execute with the available environment.
6. Claim the task before substantial work.
7. Create a unique branch named `agent/<pod>/<task-id>-<slug>`.

## What matters most

The current measured 640-candidate blocker has an oracle macro F0.5 of about **0.98095** on the recorded confirmation set, while the current end-to-end confirmation score is about **0.92883**.

Therefore:
- retrieval recall is a structural bottleneck,
- matcher/decision improvements still matter,
- India is substantially weaker than the US,
- singleton false positives are high,
- France is ~15% of test anchors with no labels.

Do not spend an entire run polishing something that cannot affect the score or research throughput.

## Working style

Treat this as a scientific experiment, not a coding assignment.

Your task must have:
- one explicit hypothesis,
- a reproducible protocol,
- a baseline measured on the same slice,
- a result,
- an interpretation,
- and a recommendation.

Prefer a small decisive experiment over a sprawling rewrite.

If raw challenge data is available locally, use it through the configured dataset path. If it is not available, do not hallucinate measurements. Implement the analysis/experiment code and document the exact command for an environment that has the data.

Never commit raw challenge data, model binaries, predictions, large generated artifacts, or secrets.

Never use external business/entity data, geocoding, search engines, or forbidden identity information.

## Research behavior

Search for overlooked structure aggressively:
- source-specific noise,
- rare tokens,
- numbers and unit identifiers,
- address reorderings,
- name replacement patterns,
- difficult same-address negatives,
- common-name ambiguity,
- retrieval misses,
- cardinality behavior,
- singleton behavior,
- source asymmetry,
- country asymmetry,
- France-safe language-agnostic signals,
- calibration failures,
- candidate-rank information,
- graph/set-level consistency,
- compute bottlenecks that prevent testing stronger ideas.

Before proposing something as new, search the repo to make sure it was not already tested.

If an idea fails, record the failure. Negative knowledge is part of the output.

## Evaluation

Use the official per-entity macro F0.5, not pair accuracy.

For retrieval changes also report:
- candidate pair recall,
- candidate entity recall,
- all-matches-retrieved rate,
- blocking-oracle macro F0.5,
- candidate-count quantiles,
- runtime and memory where practical.

For matcher/decision changes also report:
- macro F0.5,
- singleton false-positive rate,
- country slices,
- relevant cardinality/error slices.

Do not tune against frozen confirmation/final-holdout data.

## Deliverables before stopping

You must leave:

1. Code or analysis script, if the task requires it.
2. Tests for changed deterministic behavior.
3. `reports/swarm/<experiment-id>-<slug>.md`.
4. One row in `experiments/REGISTRY.tsv`.
5. A commit on your branch.
6. A PR containing the exact benchmark command and measurements.
7. A status: PROMOTE, REPLICATE, REJECT, or FOLLOW-UP.
8. At most a few evidence-backed follow-up tasks.

Do not merge your own experimental PR into `main` unless the coordinator explicitly authorizes it.

## Final rule

Do not optimize for looking productive. Optimize for information gained per minute and expected leaderboard value.

Find something specific, test it properly, write down what happened, and get out of the way so the next agent can move.
