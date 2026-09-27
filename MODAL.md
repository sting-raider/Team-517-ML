# Run the challenge pipeline on Modal

## Integrated neural32 pipeline (INT005 / M017 / INT006)

The current research integration starts from the prepared INT003 DuckDB and
depth-10 model. Train the licensed multilingual record encoder and pair
cross-encoder, build complete country-specific target indexes, then score the
test set. The measured US/India development holdout macro F0.5 is 0.970702,
versus 0.944783 for v3 on the same anchors. France and leaderboard accuracy
remain unknown until organizer evaluation.

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
modal run modal_dense.py
modal run modal_crossencoder.py
modal run modal_dense_test.py
modal run modal_neural_submission.py --threshold 0.95 --dense-prior -2 --parts-per-country 4
```

The first two commands read the supplied training labels and frozen INT003
features; the third indexes all 9,969,589 test Source 2/3 records. The last
command scores country/hash partitions in resumable 5,000-anchor batches,
merges the two exact TSVs, checks that matches are inside the candidate sets,
and creates a compressed matching download. Rerunning the same command resumes
completed batch shards and rejects changed configurations.

```powershell
New-Item -ItemType Directory -Force output/submission_v5_neural32 | Out-Null
modal volume get team517-business-er project/output/submission_v5_neural32/matching_results.tsv.gz output/submission_v5_neural32/matching_results.tsv.gz
python -c "import gzip,shutil; shutil.copyfileobj(gzip.open('output/submission_v5_neural32/matching_results.tsv.gz','rb'),open('output/submission_v5_neural32/matching_results.tsv','wb'))"
python ../student_resource/utils/validate_submission.py --matching output/submission_v5_neural32/matching_results.tsv --test-dir ../student_resource/dataset/test
```

Check the decompressed SHA-256 against `reports/neural32_submission.json`.
Upload only `matching_results.tsv` during leaderboard submissions. For the
final archive, download its **same-run** `candidate_pairs.tsv` from
`project/output/submission_v5_neural32/`; do not pair it with an older run's
candidate file. That file has at most 32 pairs per Source 1 entity.

## V6 exact-name / blank-address recovery (INT007)

With the v5 output already on the private Volume, this CPU-only pass restores
candidate matches that have an exact normalized business name, an empty
provider address, and a country-unique Source-1 name. It raised the development
holdout macro F0.5 from 0.970702 to 0.972095. It uses the **unchanged v5
candidate file**; the public score remains unknown until submission.

```powershell
modal run modal_recover_blank.py
modal run modal_recover_blank.py --action compress
New-Item -ItemType Directory -Force output/submission_v6_blank_recovery | Out-Null
modal volume get team517-business-er project/output/submission_v6_blank_recovery/matching_results.tsv.gz output/submission_v6_blank_recovery/matching_results.tsv.gz
python -c "import gzip,shutil; shutil.copyfileobj(gzip.open('output/submission_v6_blank_recovery/matching_results.tsv.gz','rb'),open('output/submission_v6_blank_recovery/matching_results.tsv','wb'))"
python ../student_resource/utils/validate_submission.py --matching output/submission_v6_blank_recovery/matching_results.tsv --test-dir ../student_resource/dataset/test
```

Verify the decompressed SHA-256 against
`reports/blank_recovery_submission.json` before uploading. The local copy in
`output/submission_v6_blank_recovery/` already passed that checksum and the
organizer's matching TSV validator. For the final archive, use v5's exact
same-run candidate file from `project/output/submission_v5_neural32/`.

`modal_neural_conflict.py` is a separate optional owner-ambiguity variant.
It removes only v5-predicted links to targets claimed by multiple Source 1
businesses, keeps the exact v5 candidate set, and writes
`submission_v6_neural32_owner`. Its full-inventory development filter reduced
v5's holdout score slightly, so it was not promoted for submission.

The Modal app uses a private Volume named `team517-business-er`. It mounts the
project code from this repository; datasets, models, and predictions stay outside
Git. The dataset staging command uploads the supplied ZIP, **not the PDFs**.

From the repository root, with `modal` authenticated:

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python tools/stage_modal.py --archive --model --training
modal run modal_app.py --action prepare
modal run -d modal_app.py --action parallel-score --run-name modal_parallel_v1 --candidate-cap 160 --workers 8 --partitions 8
```

The first command only needs to be repeated if those inputs change. `prepare`
creates the DuckDB file and indexes from the ZIP. `parallel-score` runs eight
independent Modal workers, each using the existing CatBoost model and native
comparison features, then merges their sorted outputs into both official TSVs
under `project/output/modal_parallel_v1` in the Volume. Partition outputs are
checkpointed. Use `--action score` for a simpler single-worker fallback.
Keep the same run name only for an unchanged model and configuration; choose a new
run name for other experiments.

To train the tuned CatBoost checkpoints on Modal instead, run:

```powershell
modal run modal_app.py --action train
```

This consumes the staged feature arrays; it does not need to rebuild them. The
`score` action uses `submission_v1/mixed.cbm` from the Volume, whether uploaded
locally or generated by `train`.

Download the completed predictions and validate the leaderboard file:

```powershell
New-Item -ItemType Directory -Force output/modal_parallel_v1 | Out-Null
modal volume get team517-business-er project/output/modal_parallel_v1/matching_results.tsv output/modal_parallel_v1/matching_results.tsv
modal volume get team517-business-er project/output/modal_parallel_v1/candidate_pairs.tsv output/modal_parallel_v1/candidate_pairs.tsv
modal volume get team517-business-er project/output/modal_parallel_v1/completion.json output/modal_parallel_v1/completion.json
python ../student_resource/utils/validate_submission.py --matching output/modal_parallel_v1/matching_results.tsv --candidate output/modal_parallel_v1/candidate_pairs.tsv --test-dir ../student_resource/dataset/test
```

Upload `matching_results.tsv` for the leaderboard. Keep `candidate_pairs.tsv`
for the final archive. The 160-candidate budget is a first tradeoff under the
organizers' smaller-candidate-set ranking rule; its measured calibration tradeoff
is recorded in `reports/candidate_budget.json`. The full test inference has not
been scored against hidden labels.

Each scoring worker requests eight physical cores and 32 GiB RAM. At the
published Modal rates this is approximately $0.63 per worker-hour, or $5.04
per hour while all eight workers are running, before storage/network and other
charges. Check the actual Usage & Billing dashboard against the $30 plan; the
dashboard also supports a spend limit.


## Second-submission matcher (INT002)

Use `modal_v2.py` for the larger matched-pool training run. It uses the existing
complete private DuckDB inventory, rebuilds cap-160 training candidates, and
adds four corpus-frequency features, score-only dense rank, and relative
retrieval score. Model-facing rank never breaks score ties using record IDs.

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
modal run -d modal_v2.py --action train --depth 10
modal run -d modal_v2.py --action confirm --depth 10
# Run after inspecting the confirmation result:
modal run -d modal_v2.py --action score --depth 10
New-Item -ItemType Directory -Force output/submission_v2_d10 | Out-Null
modal volume get team517-business-er project/output/submission_v2_d10/matching_results.tsv output/submission_v2_d10/matching_results.tsv
```

Training fits 108,115 reference entities / 15,431,847 candidate pairs on one L4
GPU after eight parallel CPU feature workers. Models and feature caches live in
`project/experiments/int002` in the private Volume. Local reports use the
`reports/int002_` prefix. GPU floating-point reductions can cause small variation
between retraining runs even with seed 517; preserve checkpoint hashes.

The original development folds select depth and threshold. The 5,000-entity
confirmation window is hash positions 40,001–45,000; it is excluded from model
fitting and selection. `prepare-confirmation` can compute those features while
training runs, without evaluating labels or models. Do not repeatedly use this
window to tune future models.

Inference runs eight partitions and streams both merged TSVs through coverage,
format, duplicate-target, and prediction-subset checks. The ID membership scan
is skipped because candidate IDs are joined directly from the test database.
The full candidate file remains in the Volume for final-package download:

```powershell
modal volume get team517-business-er project/output/submission_v2_d10/candidate_pairs.tsv output/submission_v2_d10/candidate_pairs.tsv
modal volume get team517-business-er project/output/submission_v2_d10/completion.json output/submission_v2_d10/completion.json
```

For a new experiment, change the experiment/output paths; never reuse an old
folder after changing a model, feature definition, input database, or blocker.
INT001's ordinal-rank checkpoints are archived research and must not be used.
The `retrieval` action is an independent diagnostic study, not the selected
submission blocker. The production second-file candidate cap stays at 160.


For a slow internet connection, package the validated matching file before
transferring it. This produces exactly the same TSV after decompression:

```powershell
modal run -d modal_v2.py --action package --depth 10
modal volume get team517-business-er project/output/submission_v2_d10/matching_results.tsv.gz output/submission_v2_d10/matching_results.tsv.gz
python -c "import gzip,shutil; src=gzip.open('output/submission_v2_d10/matching_results.tsv.gz','rb'); dst=open('output/submission_v2_d10/matching_results.tsv','wb'); shutil.copyfileobj(src,dst); dst.close(); src.close()"
```

Compare the decompressed SHA256 with the completion receipt before uploading.
The confirmed checkpoint is also available locally under `artifacts/submission_v2`
(excluded from Git), for explicit `ber.predict --model artifacts/submission_v2` use.


A transfer interrupted near the end can be resumed when at most 8 MiB of the
compressed file remains. The `resume-download` action appends the exact remote
tail, checks both the compressed and decompressed SHA256 receipts, and creates
the final TSV:

```powershell
modal run -d modal_v2.py --action resume-download --depth 10
```

The completed INT002 export receipt reports 1,732,544 rows, 5,759,144 matches,
256,724,515 candidates, and PASS for cloud streaming checks. The organizer's
matching-file validator also passes on the downloaded file. The old local
`output/modal_parallel_v1/candidate_pairs.tsv.incomplete` is intentionally
named incomplete: it had the expected length but failed the cloud checksum.
Use the valid Modal Volume candidate file for the final archive.

## Third-submission character fusion (INT003)

`modal_v3.py` builds an additional name-character index, fuses lexical top 160
with character top 64 by ID-independent average-rank RRF, and scores at most 160
unique candidates per anchor. It trains a 57-feature CatBoost model on this exact
pool. The full inventory and model artifacts stay in the private Modal Volume.

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
modal run -d modal_v3.py --action prepare
modal run -d modal_v3.py --action retrieval
modal run -d modal_v3.py --action train --depth 10
modal run -d modal_v3.py --action confirm --depth 10
modal run -d modal_v3.py --action score --depth 10
modal run -d modal_v3.py --action package --depth 10
modal run -d modal_v3.py --action download --depth 10
modal run -d modal_v3.py --action resume-download --depth 10
```

The `download` action transfers 4 MiB chunks and verifies the cloud gzip SHA256;
`resume-download` verifies the decompressed SHA256 and creates
`output/submission_v3_d10/matching_results.tsv`. A full-length file from the
Volume CLI previously failed its checksum, so use this verified chunk route. The large
`candidate_pairs.tsv` audit file remains at
`project/output/submission_v3_d10/candidate_pairs.tsv` in the private Volume;
download it for the final archive. A transfer stopped near the end can also use
`resume-download` to fetch an exact remote tail of at most 8 MiB.

The v3 model's 5,000-anchor frozen confirmation (hash positions 45,001–50,000)
scored 0.950198 macro F0.5 versus 0.942285 for the v2 model on its original
candidate pool. The v3 candidate ceiling was 0.980917. See
`reports/swarm/INT003-character-fusion.md` for the paired comparison, country
slices, singleton tradeoff, and evidence limits. No public leaderboard score is
known from that local confirmation.
