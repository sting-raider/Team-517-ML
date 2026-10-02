# M018 — All-positive cross-encoder exposure

M017 sampled at most two labeled positive fragments per fit anchor while
keeping two hard negatives. M018 uses **all** labeled positives from the same
102,125 fit anchors and the same two negatives, with the same pinned
Apache-2.0 multilingual MiniLM cross-encoder. No calibration, holdout, test
labels, external identity data, or new candidate generation enters training.

The training file contains 578,464 pairs, including 374,305 positives. All
18,077 steps completed on one Modal L4 in 1,854 seconds. This is training
evidence only; loss is not the leaderboard metric. See
`reports/m018_training.json`.

The frozen 32-candidate development pool was rescored end to end using the
same CatBoost probabilities, retrieval, threshold-selection protocol, and
fit/calibration/holdout split as INT006. Calibration again selects dense
prior -2 and threshold 0.95. M018 scores **0.978856** on 4,389 calibration
anchors and **0.972458** on the 3,051-anchor development holdout, compared
with M017/V5's 0.977238 and 0.970702. V6's separate blank-address rule
scores 0.972095 on the same holdout, so M018 alone is only +0.000364 above
V6. Candidate recall and oracle are unchanged: holdout recall 0.978484 and
oracle 0.992823. Detailed counts are in
`reports/m018_capped_evaluation.json`.

M018 is therefore **not** a credible route to 0.99 by itself. A separate
France-only production rescore tests whether all-positive exposure transfers
to the unlabeled country without paying to rescore all 55.38 million test
candidates. It must preserve the frozen V5 candidate SHA per partition and
replace only French rows in V6. The public score, not a fabricated French
validation score, will determine whether that variant is kept.

The France rescore completed for all 259,452 French Source 1 records across
four resumable GPU partitions. Its merged V7 output re-applies the selected
blank-address rule, preserves the frozen candidate SHA-256
`fa286e237b9bdd31905f901d2a1449771698249d4c1dfe45dcbfa38bf647c3ec`,
and has matching SHA-256
`aafbc73e655ce51222f81b57ed5ce92198ac01dad02c17d941a342dabbfb2f0b`.
The remote completion receipt is copied to `reports/m018_france_submission.json`.
No public score has been reported for V7.
