# Team 517 — selected V13 submission (public score 0.969)

Run commands from this `business_entity_resolution` directory. All source code is under `src/`: `ber/` contains record processing, blocking, model training, scoring, and decision rules; `pipeline/` contains orchestration and CLI entrypoints. The exact selected weights are included in `models/`. No private Modal artifact or Git checkout is needed. The organizer supplies the original training/test data separately.

## Extract the submission ZIP

The ZIP uses lossless BZIP2 compression (ZIP method12) to meet the 1024 MB upload limit while retaining every exact selected checkpoint and output. Extract with 7-Zip or Python's standard library; some built-in ZIP extractors support only the older DEFLATE method. From the directory containing the ZIP:

```powershell
python -m zipfile -e Team_517_submission.zip Team_517_submission
```

Then change directory to `Team_517_submission/code/business_entity_resolution` and follow the commands below. Extracted checkpoint and TSV bytes are unchanged; this is container compression, with no quantization or model modification.

## Environment and input

Use Python 3.12. The Modal Linux images pin the CPU dependencies in `requirements.txt` and GPU dependencies listed in `requirements-gpu.txt`. GPU inference uses NVIDIA L4 and bfloat16; preprocessing/indexing uses CPU containers. Full regeneration processes roughly 10 million target records and 55 million candidate pairs, so it requires substantial disk and compute. Authenticate your own Modal account; this archive contains no credentials.

PowerShell setup (activate the environment before all subsequent commands):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
$env:PYTHONPATH=(Join-Path $PWD 'src')
modal token new
```

On Linux use `source .venv/bin/activate`, `export PYTHONPATH="$PWD/src"`, and `export TEAM517_MODAL_VOLUME=...` in place of PowerShell environment assignments. A CUDA toolkit/compiler is not required on the client. Core dependencies install from package repositories; no external business identity service is queried.

`--dataset` below is the organizer's `dataset/` directory with these original files:

```
dataset/train/train_source1.tsv
              train_source2.tsv
              train_source3.tsv
              train_ground_truth.tsv
dataset/test/test_source1.tsv
             test_source2.tsv
             test_source3.tsv
```

## Regenerate both outputs with the exact selected checkpoints

Choose a NEW volume name for a clean run. Never reuse indexes or score shards from a different model/data version. Set this same variable for every command; it is propagated to remote images. No GPU run starts merely by installing packages or staging files. The following scoring commands do incur charges in the reviewer's account.

```powershell
$env:TEAM517_MODAL_VOLUME='team517-v13-reproduce-20261002'
python -m pipeline.verify_manifest --outputs ../../output
python -m pipeline.stage_selected --dataset C:/path/to/student_resource/dataset
modal run src/pipeline/modal_app.py --action prepare
modal run src/pipeline/modal_v3.py --action prepare
modal run src/pipeline/modal_dense_test.py
modal run src/pipeline/modal_neural_submission.py --threshold 0.95 --dense-prior -2 --parts-per-country 4
modal run src/pipeline/modal_recover_blank.py
modal run src/pipeline/modal_final_owner.py
New-Item -ItemType Directory -Force -Path output | Out-Null
modal volume get $env:TEAM517_MODAL_VOLUME /project/output/submission_v13_owner_country/matching_results.tsv output/matching_results.tsv
modal volume get $env:TEAM517_MODAL_VOLUME /project/output/submission_v13_owner_country/candidate_pairs.tsv output/candidate_pairs.tsv
```

Replace the example input path. The first preparation step imports supplied records and builds BOTH train/test lexical indexes. The second creates the character indexes. Four country-specific ANN shards per country index the entire supplied test Source 2/3 inventory. Scoring first freezes 16 neural neighbors plus the highest lexical/character candidates at cap32, then applies the CatBoost/cross-encoder ensemble (`threshold=0.95`, `dense_prior=-2`). Missing-address recovery considers only that frozen candidate file. V13 resolves existing competing owners at address/margin gates India50/5, US20/2, France20/2. It never introduces a new candidate.

The last remote step runs full ID/row/candidate-subset validation. To validate independently using the supplied organizer utility:

```powershell
python C:/path/to/student_resource/utils/validate_submission.py --matching output/matching_results.tsv --candidate output/candidate_pairs.tsv --test-dir C:/path/to/student_resource/dataset/test
```

The archived leaderboard output is byte-for-byte the submitted V13 file. Its hashes are:

```
matching_results.tsv  2d4ca5400f2e87daf886c5f4c8e1c0769720a2dd889dfd9e2de149f848199e3a
candidate_pairs.tsv  fa286e237b9bdd31905f901d2a1449771698249d4c1dfe45dcbfa38bf647c3ec
```

There are 1,732,544 Source 1 rows, 55,384,406 candidate edges, 5,683,583 predicted links, and 101,484 empty predictions in the archived outputs. Verify the archive originals with `python -m pipeline.verify_manifest --outputs ../../output`; compare a regenerated original-test run using `--outputs output`. Different input data naturally has different hashes. A fresh DuckDB import can change physical row order; this changes the ANN training sample because it is selected in row order. GPU arithmetic, ANN rebuilding, and dependency/hardware differences can therefore change regenerated candidates and near-tie results; supplied exact checkpoints avoid nondeterministic retraining but do not imply bitwise equivalence on every hardware configuration. A full fresh-volume rescore was not rerun during final packaging.

## Train from the supplied labels (optional)

This alternative documents how the selected models were learned. Training from scratch is reproducible in procedure, but GPU reductions and early stopping may yield different weights. Use the saved weights above when auditing the submitted result. Use another NEW volume name and do not stage the final saved weights into it.

The historical baseline provides comparison probabilities during CatBoost training; it is not a fourth final model. Build its data and sampled lexical pool locally:

```powershell
$env:TEAM517_MODAL_VOLUME='team517-v13-retrain-20261002'
New-Item -ItemType Directory -Force -Path artifacts,reports | Out-Null
python -m ber.data --data C:/path/to/student_resource/dataset --db artifacts/data.duckdb --report reports/data_audit.json
python -m ber.blocking --db artifacts/data.duckdb --split train --anchors 30000 --cap 80
python -m ber.experiment --db artifacts/data.duckdb --out artifacts/submission_v1 --report reports/submission_v1.json
python -m ber.blocking --db artifacts/data.duckdb --split test --anchors 1 --cap 80
python -m pipeline.stage_modal --database --model
modal run src/pipeline/modal_v2.py --action train --depth 10
modal run src/pipeline/modal_v3.py --action train --depth 10
modal run src/pipeline/modal_dense.py --action train
modal run src/pipeline/modal_crossencoder.py --action train
```

Then run `modal_dense_test.py` onward from the inference sequence. The scratch branch stages the prepared database, so it does not need raw dataset staging or `modal_app --action prepare`. `modal_v3 --action train` builds character indexes and the eight feature partitions required by neural hard-negative preparation. Calibration uses macro F0.5 on entity-disjoint training folds; labels never populate test candidates. Seed517 is recorded in code and included training reports. E5 training completed 2,128 steps on 102,125 fit anchors; M017 completed 12,578 steps over 402,483 pairs. Checkpoint time budgets did not interrupt the selected training runs.

Model revisions, licenses, modification notices, and parameter counts are in `MODEL_LICENSES.md` and `licenses/`. The methodology is `../../Documentation_template.md`.
