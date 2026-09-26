# INT006 — full-inventory neural blocker and pair reranker at 32 candidates

## Hypothesis

V3's 160-pair lexical/character blocker misses many true links, especially in India. Adding nearest neighbors from a learned multilingual record encoder should recover these links without creating an enormous final candidate file. The multilingual pair cross-encoder can then classify the new, harder pairs.

## Change

For each S1 record, search country-matched S2/S3 records in four Faiss IVF2048-SQ8 target shards. The indexes contain **every** target record from the relevant supplied split, not a truth-filtered subset. Take the 16 nearest unique records, then fill to 32 with the highest-ranked v3 fused lexical/character candidates (retrieved at internal cap 160). This occurs before matcher scoring. `candidate_pairs.tsv` records exactly these final 32 or fewer candidates.

On the final 32 pairs, the M017 cross-encoder scores every pair. A base lexical/character pair also receives its INT003 CatBoost score. Calibration chose `logit(CatBoost probability) + cross-encoder logit` for base pairs, `cross-encoder logit - 2` for dense-only pairs, and a single final probability threshold of 0.95. The dense prior and threshold were selected on 4,389 calibration anchors, then fixed for the 3,051-anchor development holdout. All record text comes from the supplied TSVs; IDs are used for joins and deterministic ties only.

The complete test inventory of 9,969,589 S2/S3 records is already encoded and indexed by country. `modal_neural_submission.py` scores disjoint country/hash partitions, checkpoints each batch, merges sorted TSVs, and invokes the existing exact candidate/matching validator. A 100-anchor French production probe completed successfully. The full test run is in progress.

## Measured results

| Same anchor set | V3 candidate pool and matcher | INT006 32-pair pool and ensemble | Gain |
|---|---:|---:|---:|
| Calibration, all (4,389) | 0.949121 | 0.977238 | +0.028117 |
| Holdout, all (3,051) | 0.944783 | 0.970702 | +0.025919 |
| Holdout, India (1,212) | 0.917541 | 0.968360 | +0.050819 |
| Holdout, US (1,839) | 0.962737 | 0.972246 | +0.009508 |

Candidate pair recall on holdout is 0.978484 at 32 pairs, compared with v3's 0.945069 at 160 pairs. The blocking oracle rises to 0.992823 overall on holdout; its India slice rises from 0.965995 to 0.991419. The model still leaves 0.022121 macro points below the new oracle, so there is substantial matcher headroom. Calibration singleton false-positive rate falls to 1.59%; holdout is 6.03%.

A cheaper compact variant that retrieves only 32 v3 candidates internally scored 0.969242 on holdout, 0.001460 below the selected full-rank variant. Both variants write at most 32 final candidates. The selected production code uses the full-rank variant because accuracy is the priority, while the small final candidate file addresses the organizer's ranking criterion.

## Risks and next step

The local splits have been used repeatedly and France has no labeled data. The 0.970702 number is a development holdout result, **not** a public/private leaderboard score or a claim that 0.998 has been reached. The full test output must finish, pass format and candidate-subset validation, and then be uploaded to measure the actual leaderboard effect. Preserve the v3/v4 files until that score is known. The final archive must include the exact candidate file from this same run, the final matching file, runnable code, and the organizer's methodology template.

The cross-encoder and encoder checkpoints are kept only on the private Modal volume; their base revisions, licenses, and parameter counts are recorded in the INT005/D017 and M017 reports. The training, retrieval, and inference code in this branch recreates the pipeline without any external business lookup.
