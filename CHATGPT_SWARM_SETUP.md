# ChatGPT Swarm Setup

The swarm is intended to run as many **ChatGPT chats inside one shared ChatGPT Project**, not as local autonomous processes.

## Why this layout

A shared ChatGPT Project gives every project chat access to the project's uploaded files, project instructions, and project conversation context. The GitHub repository remains the source of truth for code, experiment state, and reports.

The raw challenge dataset is too large to be a single ChatGPT spreadsheet upload, so prepare it as lossless TSV shards. Do **not** sample it for the shared source. Agents may sample during experiments, but the project source should preserve the entire dataset.

## Prepare project-safe shards

From the repository root:

```powershell
python tools/prepare_chatgpt_dataset.py --data ..\student_resource\dataset --out chatgpt_dataset
```

The script:

- recursively finds the challenge TSVs,
- splits them only at row boundaries,
- repeats each original header in every shard,
- preserves every row exactly,
- targets files below the ChatGPT spreadsheet upload ceiling,
- writes checksums and row counts to a local manifest,
- and fails if the resulting shard count exceeds the configured project budget.

Default target: 44 MiB per TSV shard, maximum 25 shards.

The local `manifest.json` is for verification. If all 25 project file slots are needed for data, paste the manifest summary into the Project Instructions instead of uploading it.

## Shared Project

1. Create one ChatGPT Project for the challenge.
2. Invite all four human teammates.
3. Upload every generated `.tsv` shard to the Project.
4. Put the orchestration prompt below into Project Instructions.
5. Give each research hypothesis its own chat.
6. Give every chat the repository URL and ensure the human account running that chat can access the private repository.
7. Keep all agent chats inside this same Project so they share the dataset and instructions.

Recommended Project Instructions:

```text
You are one research agent in the Team 517 Amazon ML Challenge swarm.

The complete challenge dataset has been uploaded to this Project as lossless TSV shards. Treat those Project files as the canonical raw dataset. Do not assume the data is on a local filesystem and do not ask the human to rerun analysis locally merely because the dataset is large. Use the available file-analysis tools to inspect/materialize the Project files and use Python/data-analysis tools when computation is required.

The GitHub repository sting-raider/Team-517-ML is the source of truth for code, experiment state, reports, AGENTS.md, SWARM_BACKLOG.md, and experiments/REGISTRY.tsv.

At the start of every task:
1. Read AGENTS.md and SWARM_PROMPT.md from the repository.
2. Check open issues/PRs and the experiment registry.
3. Verify you can access the Project dataset shards.
4. Claim one unclaimed atomic experiment.
5. Run the experiment yourself against the Project dataset whenever the available tools permit it.
6. Never invent measurements.
7. Commit code/report/results to your own experiment branch and open a PR.

Optimize official per-entity macro F0.5 and information gained per unit time. Preserve the frozen holdout and competition rules.
```

## Dataset access inside an agent chat

An agent should not try to place all ~1 GB of raw text into the language-model context. That is neither necessary nor useful.

Instead it should:

1. identify the needed Project shards,
2. use file tools or Python to stream/read them,
3. compute statistics / build an index / run the experiment,
4. keep only summaries and selected diagnostic examples in model context,
5. write aggregate results back to the GitHub experiment report.

For analyses that truly require all files, process them incrementally. For example, token-frequency, corruption-pattern, duplicate, cardinality, and distribution audits can stream through every shard without loading the full dataset at once.

## Human launch pattern

Each teammate can open many chats in the same shared Project. Start each chat with the contents of `SWARM_PROMPT.md` or a short instruction such as:

```text
Follow the Project instructions and SWARM_PROMPT.md. Pick the highest-value unclaimed P0/P1 experiment you can execute end-to-end with the Project dataset. Claim it, run it, record the result, commit it on an experiment branch, and open a PR. Do not duplicate active work.
```

Agents should coordinate through GitHub claims/PRs, not by relying on another chat's transient context.
