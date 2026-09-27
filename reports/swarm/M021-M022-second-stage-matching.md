# M021/M022 — second cross-encoder and learned decision layer

## Objective and protocol

The public leaderboard advanced from 0.961 (V5) to 0.969 (V12), still well short of the team's 0.99 objective. The frozen 32-candidate blocker has a 0.992823 blocking-oracle macro F0.5 on the 3,051-anchor labeled holdout. Most remaining loss is therefore within-candidate matching, although the blocker must also improve for a 0.998 result to be possible.

M021 fine-tuned an Apache-2.0 BGE reranker on **all** available positives for 102,125 fit anchors. It used only supplied business records and labels. The independent M017 cross-encoder and the existing INT003 CatBoost matcher were kept. M022 exported the exact same 237,272 frozen candidate pairs covering 4,389 calibration and 3,051 holdout anchors, with both neural logits, CatBoost probabilities, and truth. Models fit on one deterministic half of calibration; thresholds were selected on the other half; holdout was evaluated once per variant. IDs were joins/group keys, never predictive features. France has no labels and is not represented in the holdout scores.

| Rule on the same 3,051 holdout anchors | Macro F0.5 |
|---|---:|
| M017+CatBoost V5 | 0.970702 |
| V6 exact-name, blank-address recovery | 0.972095 |
| M021 cross-encoder alone, best calibrated prior | 0.974255 |
| M017/CatBoost learned stacker | 0.977317 |
| M017+M021+CatBoost learned stacker | **0.980040** |
| Dual stacker with predicted-fragment support | 0.980413 |
| Dual stacker with separate blank-address expert | **0.980673** |
| Frozen cap32 blocking oracle | 0.992823 |

The last two variants are research measurements, not production submissions. The dual stacker requires scoring M021 on the full 55.4 million-pair test pool. That rescore exceeds the remaining Modal credit. The user explicitly capped spend at the $30 credit, so no full run was launched. The current public best remains V12 at **0.969**, reported by the user. Local holdout and public scores are different quantities; none of the table entries predicts a 0.99 public result.

## Error analysis

M017 and M021 are complementary but share many hard errors on the identical holdout pool: M017 misses 437 true candidate links, M021 misses 360, and both miss 329. The depth-6 dual stacker leaves 314 pair errors: 279 false negatives and 35 false positives. Many missed positives have a blank provider address, but indiscriminately recovering name-similar blank-address candidates is harmful. Even a 1.0 token-set name match plus Source-1 exact-name uniqueness added 61 true and 127 false links to the dual stacker on holdout, dropping macro F0.5 to 0.972434. This differs from V6 because the stronger stacker already filters many deceptively exact-name negatives.

The dedicated blank-address expert produced a small, coherent gain (+0.000633 over dual stacker), and fragment-agreement features produced +0.000373. Neither supports a claim that the present architecture can reach 0.99 within the available scoring budget. Wider same-family retrieval at cap160/dense64 raises the holdout blocking oracle only to 0.996467 at about five times the candidate scoring cost. A genuinely larger improvement needs both a better shortlist and a matcher trained to distinguish the deliberately hard name/address collisions.

## Reproducibility and status

- `modal_crossencoder_m021.py` trains the pinned M021 model; `reports/m021_training.json` records initialization, license, time, and steps.
- `modal_capped_m021.py` evaluates it on the exact frozen cap32 pool; `reports/m021_capped_evaluation.json` records all calibration/holdout slices.
- `modal_export_capped_labels.py` exports only the sampled labeled candidate decisions for local CPU experiments. The row-level export and all model weights stay under ignored `artifacts/`, never Git.
- `tools/experiments/stacked_matcher_experiment.py` and `reports/stacked_matcher_experiment.json` record training, threshold selection, and ablations. The selected single-neural stacker has a completed 100-anchor France production probe, but the full submission is unscored and not promoted.
- All active Modal apps from these experiments were stopped; no beyond-credit spend was authorized.

The development holdout has been reused extensively, so modest gains are vulnerable to repeated-experiment selection. Preserve V12 until a new leaderboard file is produced and evaluated.
