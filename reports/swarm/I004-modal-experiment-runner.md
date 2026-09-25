# I004 — Modal batch runner for registered swarm experiments

## Hypothesis

A generic, provenance-safe Modal entrypoint that runs atomic `ber.*` experiment
modules against the existing private `team517-business-er` Volume will remove the
current ChatGPT Drive transfer bottleneck for full-data work and reduce duplicated
one-off Modal plumbing across retrieval, matcher, and decision agents.

This task was selected after verifying live Drive access and confirming that
`train_source2.tsv` (489,301,488 bytes) and `train_source3.tsv` (503,705,637
bytes) exceed the connector's practical 256 MiB raw-download ceiling. R001 had
already released its claim for exactly this reason, while the active retrieval
experiments R002/R014 were claimed by other agents.

## Change

Added two additive infrastructure files without modifying model, blocker, scorer, or
submission behavior:

- `modal_experiment.py`: standard-library-only experiment-spec validation,
  deterministic config hashing, safe required-Volume paths, argument placeholder
  expansion, and local dry-run output.
- `modal_experiment_app.py`: isolated Modal app using the existing private Volume,
  8 CPUs / 32 GiB RAM, exact Git branch+commit provenance, required-input preflight,
  unique output directories, RUNNING/PASS/FAIL `run.json` metadata, and environment
  variables for the shared DB/dataset/run paths.
- `tests/test_modal_experiment.py`: focused deterministic/safety tests.
- `MODAL.md`: usage and handoff documentation.

The launcher executes Python directly as
`python -u -m ber.<module> ...`; it does not invoke a shell. It refuses dirty Git
worktrees and refuses to overwrite an existing run directory.

## Protocol

Tier: 0/1 infrastructure validation.

Repository baseline: main at `2a2ae6ec6de943ad7e38ecc0f0a95b53a0d7f460`.

Branch: `agent/i/I004-modal-experiment-runner`.

Local validation performed in the available Python/container runtime:

```text
python -m py_compile modal_experiment.py modal_experiment_app.py tests/test_modal_experiment.py
python -m unittest discover -s tests -v
python modal_experiment.py \
  --experiment-id R003 \
  --module ber.retrieval_char_address \
  --args-json '["--db","{db}","--out","{run_dir}"]' \
  --required-paths-json '["project/artifacts/data.duckdb"]' \
  --code-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --branch agent/r/R003-char-address
```

The current ChatGPT runtime has GitHub, Drive metadata/file access, Python/container,
and web access, but no direct Modal connector or authenticated Modal CLI. Therefore
no remote compute run is claimed.

## Results

Baseline: no generic swarm experiment runner existed. Existing `modal_app.py`
contains fixed actions for database preparation, CatBoost training, and submission
scoring, so new atomic experiments otherwise need bespoke Modal functions.

New result:

- 4/4 focused unit tests PASS.
- Python syntax compilation PASS for helper, Modal app, and tests.
- Dry-run spec generation PASS.
- Identical experiment inputs produce identical SHA-256 config hashes/run names.
- Changing arguments or code SHA changes the config hash.
- Unsafe `../` Volume requirements are rejected.
- Non-`ber.*` module execution is rejected.
- `{db}`, `{dataset}`, `{volume}`, and `{run_dir}` placeholders resolve to the
  intended private-Volume paths.
- Remote runner records branch, commit SHA, args, required inputs, config hash,
  resource request, timestamps, duration, return code, and status.
- Existing run directories are never silently overwritten.

No official macro F0.5, candidate recall, or retrieval oracle metric changes are
claimed because this experiment intentionally does not alter the model or candidates.

## Error analysis

The main failure modes addressed are infrastructure/reproducibility failures:

1. **Drive size wall**: full S2/S3 files cannot be pulled into this chat runtime.
   Modal experiments can instead consume the already-staged DuckDB/Volume data.
2. **Stale/unidentifiable code**: a dirty local checkout is rejected before launch,
   and exact branch/SHA are recorded.
3. **Config ambiguity**: normalized args + required inputs + code provenance are
   hashed into a stable config ID.
4. **Artifact collision**: runs get isolated Volume directories and overwrite is
   rejected.
5. **Shell injection / quoting drift**: only a dotted `ber.*` module is executed
   through an argv list, never `shell=True`.
6. **Missing staged input**: required Volume paths are checked before compute starts.

## Interpretation

This does not improve the score by itself. It targets a live throughput blocker that
already prevented R001 from executing and would otherwise force every full-data
agent to reimplement remote execution. Because it is an additive app, it does not
risk changing the selected first-submission pipeline.

The highest-value use is for retrieval experiments that need the complete target
inventory and can expose a CLI module accepting `{db}` and `{run_dir}`, or read
the `TEAM517_*` environment variables.

## Risks

- A real Modal invocation was not possible from this ChatGPT runtime, so Modal API
  compatibility and private-Volume visibility still need one authenticated smoke run.
- The generic worker has a fixed 4-hour timeout, 8 CPUs, and 32 GiB RAM. Experiments
  outside that envelope need a deliberate runner extension rather than silently
  changing resources.
- The runner cannot prevent an experiment module from writing large or row-level
  artifacts to its private Volume directory. Repository rules still prohibit
  committing those artifacts to Git.
- Code outside `src/ber` is intentionally not executable through this runner.
  Agents should keep atomic experiment entrypoints as `ber.*` modules.
- This runner records provenance but does not automatically update
  `experiments/REGISTRY.tsv`; the agent remains responsible for aggregate result
  reporting after the run.

## Recommendation

**PROMOTE** as additive research infrastructure, with one authenticated Modal smoke
run before expensive experiments rely on it. It changes no model/scoring path and
directly addresses the observed full-data access bottleneck.

## Follow-up tasks

1. First full-data agent with Modal CLI access: run a tiny read-only `ber.*` smoke
   module through `modal_experiment_app.py` and checkpoint the resulting
   `run.json`.
2. Retrieval agents R003/R005/R006/R007 can reuse this runner instead of adding
   experiment-specific Modal wrappers, provided their entrypoint accepts the shared
   DB/run paths.
