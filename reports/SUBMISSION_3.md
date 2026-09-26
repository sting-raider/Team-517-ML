# Submission 3: INT003 lexical and character fusion

The selected v3 pipeline combines the existing lexical blocker with name-character 3/4-gram retrieval, fuses the two ranked lists, and keeps at most 160 unique candidates per Source 1 entity. A depth-10 CatBoost model trained on that exact candidate distribution scores 57 features. Its threshold is 0.625, chosen only on development calibration labels. The checkpoint is saved privately at `team517-business-er/project/experiments/int003/depth10/mixed.cbm` and locally under `artifacts/submission_v3/`; it is not in Git.

On the frozen 5,000-anchor hash window 45,001–50,000, v3 scored **0.950198 macro F0.5** versus **0.942285** for the previous full v2 pipeline on the same anchors. The paired gain is **0.007914**, entity-bootstrap 95% interval **[0.005892, 0.009956]**. India improved from 0.922066 to 0.932699; the US from 0.956013 to 0.962081. India singleton false positives rose from 6/114 to 8/114, a documented tradeoff. The v3 candidate ceiling is 0.980917 on this window, so this configuration cannot reach 0.998 on a population with the same retrieval difficulty even with a perfect matcher. France has no supplied labels and is not covered by these metrics.

The character-fusion retriever increased mean calibration candidates from 142.18 to 148.05 while retaining the hard cap of 160. The measured calibration pair recall rose 0.925308 to 0.944357 and oracle macro 0.973081 to 0.980461. The fusion uses score-only average ranks for retrieval ties, so RRF weights do not encode target IDs. See [INT003 report](swarm/INT003-character-fusion.md) for the protocol, full slices, and comparison details.

## Reproduce

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
modal run -d modal_v3.py --action prepare
modal run -d modal_v3.py --action retrieval
modal run -d modal_v3.py --action train --depth 10
modal run -d modal_v3.py --action confirm --depth 10
modal run -d modal_v3.py --action score --depth 10
modal run -d modal_v3.py --action package --depth 10
```

The private Volume stores both final TSVs and the full model/feature artifacts. `matching_results.tsv` alone is the leaderboard upload; `candidate_pairs.tsv` is required in the final archive and must match the actual candidates scored. No portal submission slot is consumed by this pipeline.

## Export status

Full test scoring completed on eight Modal workers. The cloud streaming validator reports **PASS**: 1,732,544 reference rows, 264,828,881 candidate pairs, 5,819,438 predicted matches, and 102,598 empty predictions. The candidate file contains 8,104,366 more pairs than v2 (about 4.68 more per reference entity); its full-test mean is 152.86 candidates per entity. This quality-versus-audit-size tradeoff accompanies the confirmed local macro gain.

- Matching SHA256: `bf712f4d4fee94e56487b614ef302752bbcb2d2699e2fb65637aaf7fc32f4539`
- Candidate SHA256: `56333f15abb4eecc99d11db07b8a5a4d56d7b2763fd7b1727a6c0debe7a195e3`
- Model SHA256: `9e25404658ae5fd0723d4beda55766c40f45b69d33ecf3f039d250994f4d73b9`
- Private candidate audit: `project/output/submission_v3_d10/candidate_pairs.tsv` on the `team517-business-er` Modal Volume.
- Cloud validation receipt: `reports/int003_depth10_export.json`.

The verified leaderboard file is `output/submission_v3_d10/matching_results.tsv` locally (excluded from Git). Chunked transfer, decompression, and SHA256 checks all passed. The organizer's `validate_submission.py` reports **PASS** for its matching-file format and row coverage. The cloud validator reports **PASS** for the full candidate/matching pair, including prediction-subset and duplicate checks. Candidate IDs are obtained by joining the supplied test inventory; the optional exhaustive ID-existence scan was not run.

An unlabeled test-country audit found that v3 predicts 4.36 matches per French reference entity on average, versus 4.57 for v2; India rises from 2.98 to 3.08 and the US from 3.25 to 3.31. These counts only flag possible distribution shifts, not correctness. In particular, the French reduction could improve precision or lose recall; no French labels are available. See `reports/int003_test_country_drift.json`. The candidate file remains private on Modal until the final archive is assembled.
