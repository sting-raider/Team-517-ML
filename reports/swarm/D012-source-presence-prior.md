# D012 — Source-presence priors from Source-1 evidence

## Hypothesis

Inference-safe Source-1 structure may predict whether a labeled anchor has any Source-2 match, any Source-3 match, or both-source support even though D001a found no useful Source-1-only singleton signal. A stable signal would justify testing soft source-aware priors in D004/D008 or expected-F0.5 decoding.

## Change

No production/model code was changed. This run established the exact full-data protocol and attempted to execute it on the complete supplied Source-1 and ground-truth files.

## Protocol

Inputs verified and downloaded from the connected challenge Drive:

- `train_source1.tsv`: 210,069,713 bytes
- `train_ground_truth.tsv`: 127,015,583 bytes
- both files were successfully transferred by the Drive connector and mounted as raw TSVs
- `train_source2.tsv`: 489,301,488 bytes and `train_source3.tsv`: 503,705,637 bytes were also verified in Drive but are not required for this task and exceed the connector's 256 MiB raw-download ceiling

Planned labels: S2-present, S3-present, both-source, S2-only, S3-only from supplied truth IDs. Planned predictors: Source-1 name/address missingness, lengths, token/digit/punctuation structure, and label-free normalized collision frequency. Entity IDs would be used only for the repository's `fold517` assignment, never as predictive features.

Planned evaluation: complete population prevalence plus held-out fold517 AUROC/AUPRC/Brier and US/India slices; no confirmation/frozen holdout consumption.

## Execution result

**BLOCKED by the current ChatGPT compute runtime.**

The data plane is working: Drive access was verified and both required raw files were mounted successfully. However, every available local execution backend failed before user code began:

- private Python analysis backend: session-level `ClientError`
- user-visible Python backend: session-level `ClientError`
- container shell, including a trivial `echo`: session-level `ClientError`

This is therefore a compute-session failure, not a data-access failure and not a model/result.

A separate attempt to download Source-2 through Drive confirmed the live connector still rejects files above 268,435,456 bytes; that limitation is unrelated to D012 because S2/S3 text is unnecessary here.

## Baseline

Context only, not re-evaluated:

- selected confirmation macro F0.5: 0.928835
- singleton false-positive rate: 10.65% overall / 13.51% India
- D001a Source-1-only singleton holdout AUROC: 0.500142
- D006a: 85.2404% of non-singletons have both-source truth support; S2/S3 positive-count correlation 0.1199

## Results

No predictive metric was produced. No sample or proxy dataset was substituted for the requested full-data analysis.

## Error analysis

The failed execution itself establishes three useful capability facts for swarm scheduling:

1. The shared Drive source is reachable and the two sub-256-MiB files required by S1/truth-only experiments can be mounted.
2. The >256-MiB S2/S3 connector limit remains real.
3. This chat's local compute service is unavailable independently of file transfer, so an empirical result from this run would be fabricated.

## Risks

- No competition inference was run.
- No confirmation/frozen holdout was consumed.
- No external business/entity data was used.
- No raw challenge records or row-level diagnostics are committed.

## Recommendation

**BLOCKED / FOLLOW-UP.** Recover this bounded experiment in a chat/runtime with functioning Python/container execution. Do not infer source-presence priors from D006a aggregate prevalence alone, and do not add anchor-only source priors to the decision layer without held-out evidence.
