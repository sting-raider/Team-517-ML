# INT007 — recover exact-name records with missing provider addresses

V5 misses some true links already inside its frozen 32-candidate blocker. A diagnostic of its held-out errors found that many of these targets have an empty normalized address despite an exact normalized business-name match. The neural pair score often vetoes them. Adding every exact-name/blank-address candidate is unsafe: it adds 452 false links and only 91 true links on holdout.

The selected rule adds a candidate only when its normalized name exactly equals the Source-1 normalized name, its normalized address is empty, and that Source-1 name is unique among same-country Source-1 records. It uses only supplied record text and the existing v5 candidate file. It requires no extra neural inference, does not increase the candidate cap, and adds no target outside `candidate_pairs.tsv`.

| Same v5 candidate pool | V5 macro F0.5 | Recovery macro F0.5 | True links added | False links added |
|---|---:|---:|---:|---:|
| Calibration, 4,389 anchors | 0.977238 | 0.977942 | 51 | 9 |
| Holdout, 3,051 anchors | 0.970702 | 0.972095 | 44 | 3 |

The calibration/holdout sets have been reused for many experiments, so these figures are development measurements, not a guarantee of a leaderboard increase. A relaxed fuzzy-name variant scored slightly worse on calibration and offered no meaningful held-out gain, so the exact rule was retained. Exact target-to-target name/address cluster completion added zero links and was rejected. Re-filtering v5 by D017 reverse owners also hurt held-out score and was rejected.

The full test CPU pass changed 24,146 Source-1 rows and added 25,143 links (France 5,798; India 8,071; US 11,274), all selected from the unchanged v5 candidate set of 55,384,406 pairs. The candidate file SHA-256 remains `fa286e237b9bdd31905f901d2a1449771698249d4c1dfe45dcbfa38bf647c3ec`; the new matching file SHA-256 is `ab1b41964cdfbbccb4956c47d362d6c9b08cf7de73d67c3c8b66a963f61010e5`. The 32-pair blocking ceiling remains about 0.993 on holdout, and matcher errors still dominate the gap to the team's 0.998 ambition.

Reproduction: `modal run modal_recover_blank.py` after the v5 run. Source: `src/ber/recover_blank.py`. Output: private Modal volume path `project/output/submission_v6_blank_recovery/matching_results.tsv`, plus a local copy in `output/submission_v6_blank_recovery/` after download. `reports/blank_recovery_submission.json` records counts and checksums. The exact v5 candidate file is retained privately for the final archive; it need not be downloaded for leaderboard upload.
