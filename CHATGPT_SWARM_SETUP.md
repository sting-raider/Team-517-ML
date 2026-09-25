# ChatGPT Swarm Setup

The swarm is intended to run as many **ChatGPT chats inside one shared ChatGPT Project**, launched by the four teammates. These are not assumed to be local agents.

GitHub is the durable coordination plane. Google Drive is the shared raw-data plane. The ChatGPT Project is the shared instruction/context plane.

## Recommended topology

```
Google Drive shared folder
  complete raw challenge dataset
            |
            v
Shared ChatGPT Project
  project instructions + Drive folder source
            |
   many independent chats
            |
            v
GitHub issues / claims / branches / PRs / experiment registry
```

## Primary dataset route: Google Drive

Do **not** commit the raw dataset to GitHub.

Create one ordinary Google Drive folder in My Drive, for example:

`Amazon ML Challenge 2026 - Dataset`

Put the complete extracted challenge dataset there with the original train/test structure intact.

Share that folder directly with all four teammates' Google accounts. Use an ordinary shared folder rather than relying on a Google Shared Drive because current ChatGPT Google Drive browsing support is centered on My Drive and items shared directly with the connected account.

Each teammate must connect **their own** Google Drive account to ChatGPT. One teammate connecting Drive does not transfer that teammate's Google authorization to everybody else.

Then add the Google Drive folder URL to the shared ChatGPT Project as a Project Source.

Important: Google Drive content added in a Project is accessed live when needed; it is not pre-synced into every chat. Agents must explicitly use the Drive source when an experiment needs raw data.

## How a ChatGPT research agent should read the dataset

A research chat must not try to place ~1 GB of TSV text into conversational context.

For an empirical task it should:

1. Read `AGENTS.md` and `SWARM_PROMPT.md` from GitHub.
2. Find and claim one experiment.
3. Access the shared Google Drive dataset folder.
4. Locate only the source files needed for that experiment.
5. For a large TSV, obtain the complete raw file into the chat's working analysis environment rather than asking for the entire file inline.
6. Use Python/data-analysis tools to scan or stream the file.
7. For whole-dataset analysis, process files incrementally/chunkwise.
8. Keep only aggregate statistics and selected diagnostic examples in conversational context.
9. Write compact results to `reports/swarm/`, update `experiments/REGISTRY.tsv`, commit, and open a PR.

Examples of tasks that can stream the complete dataset without loading it all into model context:

- token and character n-gram frequencies,
- source/country corruption statistics,
- positive-pair edit patterns,
- duplicate and near-duplicate audits,
- hard-negative mining,
- address-number/unit analysis,
- retrieval miss taxonomy,
- score/cardinality distributions,
- train/test and France distribution shifts.

An agent may use a smaller sample for a Tier-1 feasibility experiment, but it must not silently substitute a sample when the requested result is supposed to describe the full dataset.

## Shared Project setup

1. Create one shared ChatGPT Project for Team 517.
2. Invite the four teammates.
3. Add the shared Google Drive dataset folder URL as a Project Source.
4. Add the repository URL.
5. Put the orchestration prompt below into Project Instructions.
6. Keep every research-agent chat inside this Project.
7. Each teammate connects their own GitHub/Google Drive access as required.

Recommended Project Instructions:

```text
You are one autonomous research agent in the Team 517 Amazon ML Challenge swarm.

The complete challenge dataset is stored in the Google Drive dataset folder attached to this Project. GitHub repository sting-raider/Team-517-ML is the source of truth for code, coordination, AGENTS.md, SWARM_BACKLOG.md, reports, and experiments/REGISTRY.tsv.

At the start of every task:
1. Read AGENTS.md and SWARM_PROMPT.md from GitHub.
2. Inspect open Issues/PRs, recent progress, active claims, and the experiment registry.
3. Verify access to the Google Drive dataset source.
4. Claim one unclaimed high-value atomic experiment.
5. Execute the experiment yourself. Use the Drive dataset and Python/data-analysis tools rather than asking the human to run routine scripts locally.
6. Do not attempt to stuff the complete dataset into model context. Read large files programmatically and stream/chunk when necessary.
7. Never invent measurements. If data access genuinely fails, mark the task BLOCKED with exact evidence.
8. Preserve competition rules and frozen holdouts.
9. Commit code and compact aggregate results to your experiment branch and open a PR.
10. Leave useful follow-up tasks, then take another unclaimed task if the session still has time and capability.

Optimize official per-entity macro F0.5, retrieval oracle ceiling, unseen-country robustness, and information gained per unit wall-clock time.
```

## Launch prompt for each new chat

A short launch message is enough because the rest lives in Project Instructions and the repository:

```text
Operate as a Team 517 swarm agent. Follow the Project instructions and AGENTS.md. Inspect live GitHub state, claim the highest-value unclaimed experiment you can execute end-to-end, use the shared Drive dataset yourself, run it, record measurements, commit the result on an isolated branch, open a PR, and continue onto another useful unclaimed task if time remains. Do not duplicate active work.
```

## Direct-upload fallback

If Drive access proves unreliable for a particular teammate/model, the complete dataset can instead be uploaded to the shared Project as lossless TSV shards.

Prepare shards with:

```powershell
python tools/prepare_chatgpt_dataset.py --data ..\student_resource\dataset --out chatgpt_dataset
```

The script preserves every row, repeats headers, writes checksums, and targets files small enough for Project upload. This is a fallback because Project file-count limits are much less flexible than a shared Drive folder.

## Rule of thumb

GitHub stores durable intelligence.
Drive stores bulky raw evidence.
The ChatGPT Project tells every chat how to use both.

Do not duplicate the 1 GB dataset per chat. Give every chat authorized access to the same shared source.
