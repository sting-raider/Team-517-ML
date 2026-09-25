# AGENTS.md — Team 517 Research Swarm

This repository is being used by many human-launched coding/research agents in parallel during the Amazon ML Challenge 2026. This file is the operating system for that swarm.

The goal is not "make changes." The goal is to discover, measure, and integrate changes that increase the official **per-entity macro F0.5** on genuinely unseen data.

## 0. Read this before doing anything

Before starting work, read:

1. `AGENTS.md`
2. `reports/RESULTS.md`
3. `PROJECT_DECISIONS.md`
4. `RESEARCH_STRATEGY.md`
5. `RULES_INSIGHTS.md`
6. The relevant implementation under `src/ber/`
7. Existing reports related to your idea
8. Open issues / active claims / recent PRs

Do not rediscover facts already established in the repo unless you are explicitly testing whether they are wrong.

## 1. Current measured baseline and the most important fact

As of 25 Sep 2026:

- Selected matcher: CatBoost depth 10, 47 numerical features.
- Current untouched-at-selection 5,000-anchor confirmation macro F0.5: **0.928835**.
- US confirmation: **0.948339**.
- India confirmation: **0.900722**.
- Candidate pair recall at cap 640: **0.947246**.
- Blocking oracle macro F0.5 at cap 640: **0.980951**.
- Singleton false-positive rate: **10.65% overall**, **13.51% India**.
- Test includes **259,452 French source-one entities, 14.98% of test anchors**.
- France has no labeled training examples.

Critical implication: with the present blocker, no matcher, threshold, ensemble, or clever decision rule can reach 0.998 because true links missing from the candidate set impose an oracle ceiling around 0.981 on the measured confirmation set. Retrieval is therefore a first-class bottleneck, not plumbing.

The team's aspirational goal is 0.998. Treat that as a target to attack scientifically, not as evidence that any proposed method will achieve it.

## 2. Competition constraints

Follow the supplied challenge rules. In particular:

- Use only supplied challenge entity records for entity identity evidence.
- Do not use external business registries, geocoding services, search engines, entity-resolution APIs, or internet-derived business data to identify records.
- Keep raw challenge data, archives, model binaries, predictions, row-level private diagnostics, and generated large artifacts out of Git.
- Pretrained models must satisfy the competition's parameter and license restrictions. Record checkpoint name, revision, parameter count, and license before use.
- Never use record IDs as predictive features.
- Never tune on hidden leaderboard feedback as if it were ground truth.
- Preserve raw text and deterministic reproducibility.

If a proposed trick might violate a rule, stop and document the uncertainty rather than quietly doing it.

## 3. Data access: ChatGPT Project agents

The primary swarm workers are **ChatGPT chats inside one shared ChatGPT Project**. They are not assumed to be local processes.

The complete challenge dataset lives in one shared **Google Drive folder** that is attached to the shared ChatGPT Project as a Project Source. Every human operator must have that Drive folder shared directly to their Google account and must connect their own Google Drive access to ChatGPT. One teammate's app authorization does not become another teammate's authorization.

At the start of an empirical task, a chat agent must verify that the Drive dataset source is accessible. When computation is needed, locate the required raw TSVs, bring the complete raw file into the chat's analysis environment, and use Python/data-analysis tools to stream or load it. Do not ask the human to run a local script merely because the dataset is large if the chat can execute the analysis itself.

Do **not** try to stuff the full ~1 GB dataset into conversational context. Read it programmatically, stream/chunk it, and retain only aggregate statistics and selected diagnostics in context.

The shared Modal volume `team517-business-er` remains useful for long or expensive jobs and large shared compute artifacts. Lossless Project-file shards produced by `tools/prepare_chatgpt_dataset.py` are the fallback when Drive access is unavailable.

Scripts should accept explicit input paths and avoid assumptions about one machine's directory layout.

If a chat truly lacks access to the Project dataset, it may implement code/protocol without claiming measurements, but it must mark the task BLOCKED rather than fabricate empirical results.

See `CHATGPT_SWARM_SETUP.md` for the human setup.

## 4. Swarm topology

Work is divided by research lane, not by person.

### Pod R — Retrieval / blocking / data forensics
Mission: raise true-link recall and the blocking-oracle score, especially India and future-France robustness.

### Pod M — Matcher / features / representation
Mission: reduce false positives and false negatives among retrieved candidates.

### Pod D — Decision / calibration / singleton / set-level optimization
Mission: optimize the actual per-anchor F0.5 decision, cardinality, abstention, and ambiguity handling.

### Pod I — Infrastructure / evaluation / ensembling / adversarial audit
Mission: make experiments fast, reproducible, comparable, and hard to fool.

The four humans may each run agents from any pod. Pods are domains, not ownership boundaries.

## 5. Do NOT use three giant shared experiment branches

Hundreds of agents on three shared branches will become a merge-conflict landfill.

Use:

- `main`: stable, measured baseline only.
- `integration/<topic>`: temporary branch combining several already-promising changes.
- One ephemeral branch per atomic agent task:
  `agent/<pod>/<task-id>-<short-slug>`

Examples:

```
agent/r/R017-char-ngram-retriever
agent/m/M008-address-alignment
agent/d/D004-singleton-gate
agent/i/I011-fast-slice-runner
```

Never develop directly on `main`.
Never place two unrelated hypotheses in one branch.

## 6. Claiming work

Before coding:

1. Search open issues, active PRs, `SWARM_BACKLOG.md`, and `experiments/REGISTRY.tsv`.
2. Pick one unclaimed atomic task with the highest expected information value.
3. If a GitHub issue exists, comment:
   `CLAIMED: <agent/pod> — <branch> — <UTC timestamp>`
4. Create your branch from the latest stable baseline.
5. If no issue exists, create one or add a clearly named backlog item before doing substantial work.

If another agent already claimed the same experiment, choose a different task unless your assignment is explicitly independent replication.

Duplication is useful only when it is deliberate replication.

## 7. One agent run = one atomic scientific question

Good:
- Does character 3–5 gram retrieval recover positive pairs missed by blocker v2?
- Does address-token IDF improve India precision at fixed candidate recall?
- Does a singleton-specific gate reduce false positives without hurting non-singletons?
- Does source-specific calibration beat a global threshold?

Bad:
- "Improve the model."
- "Research entity resolution."
- "Try some features."
- "Analyze everything."

Each run should produce an answer, not a cloud of vibes.

## 8. Experiment funnel

Do not launch every idea over 24 million rows.

### Tier 0 — Static / forensic
Code inspection, report analysis, distribution audit, failure taxonomy, complexity estimate.

### Tier 1 — Micro
Hundreds to a few thousand anchors. Used to catch broken ideas and estimate runtime.

### Tier 2 — Development
Use the designated development/calibration partitions. Compare against the exact current baseline on identical anchors.

### Tier 3 — Robustness
Country slices, cardinality slices, difficult negatives, retrieval-miss slices, ambiguity slices, source-specific slices.

### Tier 4 — Integration candidate
Run only ideas that survived earlier tiers. Combine with other independently useful changes and retune only the parameters that logically need retuning.

### Tier 5 — Coordinator-only frozen check
Do not repeatedly tune against the final holdout.

The previously reported confirmation sets must remain diagnostic references, not become the swarm's training target. Reserve a new frozen hash-ordered block beginning after all previously inspected confirmation ranges, and use it only at integration gates.

## 9. Promotion rules

A result is promotable only when all of the following are true:

- It runs reproducibly from a documented command.
- It is compared against the current baseline on the same anchors.
- It reports the official entity-level macro F0.5 when relevant.
- Retrieval changes report:
  - pair recall,
  - entity recall,
  - all-matches-retrieved rate,
  - blocking-oracle macro F0.5,
  - candidate count quantiles,
  - runtime / memory.
- Matcher/decision changes report:
  - macro F0.5,
  - singleton false-positive rate,
  - country slices,
  - cardinality slices when relevant,
  - candidate recall so we know whether the candidate set changed.
- The change has a plausible mechanism, not just a lucky threshold.
- No leakage or rule violation is detected.
- Negative tradeoffs are written down.

Tiny gains matter in a leaderboard this tight, but a one-off +0.0003 on a repeatedly inspected split is not divine revelation. Replicate fragile gains.

## 10. Mandatory experiment record

Every empirical task must add one row to `experiments/REGISTRY.tsv`.

Required fields:
- experiment ID
- issue/task ID
- pod
- owner/agent
- branch
- commit
- hypothesis
- dataset slice
- baseline metric
- new metric
- delta
- key secondary metric
- runtime
- status
- report path

Write a human-readable report under:

`reports/swarm/<experiment-id>-<slug>.md`

If useful, also write compact JSON with machine-readable metrics.

Negative results belong in the registry. Repeating failed experiments because nobody recorded them is an excellent way to waste the remaining 72 hours.

## 11. Required report structure

Every report should contain:

### Hypothesis
What exactly should improve and why?

### Change
What code / feature / retriever / decision rule changed?

### Protocol
Exact split, sample size, seed, command, hardware, candidate cap.

### Results
Baseline and new measurements side by side.

### Error analysis
At least several concrete failure categories or aggregate slices.

### Interpretation
Why did it help or fail?

### Risks
Leakage, country shift, overfitting, runtime, memory, rule uncertainty.

### Recommendation
Promote, reject, replicate, or investigate further.

### Follow-up tasks
Only evidence-backed next steps.

## 12. Highest-value research directions

### Retrieval / blocker
Prioritize methods that can increase the current ~0.981 oracle ceiling:

- character n-gram inverted retrieval,
- weighted token / BM25-style retrieval,
- rare-token and rare-number blocks,
- adaptive candidate budgets for ambiguous anchors,
- address-number + locality combinations,
- name/address mixed character retrieval,
- transliteration-tolerant representations,
- phonetic features where linguistically justified,
- reverse retrieval from S2/S3 toward S1,
- multi-stage recall-first retrieval followed by cheap pruning,
- source-specific and country-specific blocking rules,
- retrieval learned only from permitted challenge labels,
- analysis of every missed positive by corruption type.

Measure marginal recovered positives per added candidate. A retriever that adds 10,000 garbage candidates to recover one link is not automatically useful.

### Data forensics
Mine the supplied train data for:
- source-specific abbreviation patterns,
- token insertion/deletion/substitution frequencies,
- legal suffix behavior,
- address component reorderings,
- number/unit corruption patterns,
- common-vs-discriminative tokens,
- missing-address behavior,
- name-only vs address-only positive modes,
- duplicate-location / same-building hard negatives,
- country and source distribution shifts,
- positive-pair edit patterns that can inform legal normalization.

Learn transformations from challenge labels, not from the internet.

### Matcher / features
Investigate:
- corpus-frequency / IDF-weighted similarities,
- aligned character n-gram similarity,
- token-level soft matching,
- address component agreement and conflict,
- unit/floor/shop number handling,
- rare-number evidence,
- common-name penalties,
- candidate rank and retriever-source features,
- source-specific models,
- country-aware models without leaking labels,
- calibrated compact multilingual encoders permitted by rules,
- pairwise hard-negative mining,
- ensemble disagreement features.

### Decision layer
The metric is set-valued and precision-heavy. Explore:
- source-specific thresholds,
- country-specific thresholds where defensible,
- per-anchor adaptive thresholds,
- top1/top2 score gaps,
- cardinality prediction,
- explicit singleton probability,
- abstention under weak evidence,
- expected-F0.5 selection over calibrated probabilities,
- consistency between source 2 and source 3 evidence,
- graph features as evidence, not blind transitive closure.

### France robustness
France is ~15% of test anchors and unlabeled.

Investigate only methods allowed by the rules:
- language-agnostic character models,
- Unicode/diacritic handling,
- multilingual permitted encoders,
- source-format analysis of unlabeled French records,
- transformations learned from US/India that are plausibly language-independent,
- synthetic corruption derived from challenge-trained noise models,
- sensitivity checks that remove English/India-specific heuristics.

Do not invent French labels.

### Adversarial audit
Assign agents specifically to break promising results:
- check for ID leakage,
- check split contamination,
- check duplicate entities across folds,
- check accidental positive injection,
- check threshold tuning on confirmation,
- check candidate-cap mismatch,
- check cache reuse after input changes,
- check country leakage,
- check whether a gain disappears under a different entity sample.

## 13. Efficiency rules for hundreds of agents

- Prefer orthogonal work. Ten agents testing ten distinct hypotheses beat ten agents rewriting the same normalizer.
- Use existing cached feature arrays whenever the experiment does not require rebuilding them.
- Add small focused analysis scripts rather than giant notebooks.
- Scripts must be deterministic and CLI-driven.
- Cache expensive intermediate representations with config hashes.
- Never silently overwrite another experiment's artifacts.
- Use unique output directories.
- Keep aggregate reports small enough for Git.
- For expensive full-data jobs, estimate runtime on a small sample first.
- If an experiment is obviously losing, stop it early and record the result.
- Do not perform broad refactors during the hackathon unless they unlock measurable research throughput.
- Do not change scoring logic casually. The official metric implementation is sacred until proven wrong.

## 14. Code quality rules

- Preserve backward compatibility unless the experiment explicitly requires a break.
- Add tests for any new normalization, feature, scoring, blocking, or serialization behavior.
- Keep raw and normalized fields separate.
- Do not catch-and-ignore failures in evaluation code.
- Fail loudly on stale caches or mismatched configs.
- Record seeds.
- Record candidate caps and thresholds in model configs.
- Make expensive optional dependencies opt-in.

## 15. Pull request contract

An experiment PR must include:

- task / experiment ID,
- hypothesis,
- exact benchmark command,
- baseline and new measurements,
- changed files,
- runtime / resource impact,
- rules/compliance note,
- report path,
- whether it is safe to merge independently,
- interactions with other active PRs.

Do not write "improves accuracy" without numbers.

## 16. What to do when you finish

1. Commit code and report.
2. Update `experiments/REGISTRY.tsv`.
3. Open a PR.
4. Mark the issue/result as one of:
   - PROMOTE
   - REPLICATE
   - REJECT
   - FOLLOW-UP
5. Create at most a few evidence-backed follow-up tasks.
6. Stop. Do not turn one agent run into twelve half-finished experiments.

The coordinator will decide integration order.

## 17. Prime directive

Be aggressively curious and aggressively skeptical.

Search for tiny edge cases, weird source artifacts, asymmetries, corruption patterns, and metric-specific opportunities. But every "insight" must eventually cash out as one of:

- a measurable gain,
- a higher oracle ceiling,
- a faster experiment loop,
- a discovered failure mode,
- or a ruled-out idea that saves other agents time.

The swarm is not rewarded for activity. It is rewarded for information and score.
