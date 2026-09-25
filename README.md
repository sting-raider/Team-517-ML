# Team 517 — Amazon ML Challenge 2026

An executable business entity resolution baseline for the supplied name/address data.
The official target is **macro F0.5 per source-one entity**, including singletons.
This is an initial measured baseline, not a claim about leaderboard position.

**Current priority:** maximize validation quality. See `PROJECT_DECISIONS.md`.
The earlier 30-candidate throughput draft was stopped and is not a final submission.

## Local setup

Python 3.12 is tested. No GPU, cloud account, external business lookup, or pretrained
model is required by this baseline. Allow approximately 25 GB of working disk space;
the database uses a 4 GB memory limit, with additional memory for Python and training.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

The challenge data is deliberately excluded from Git. The commands below assume
the downloaded `student_resource` folder is next to this repository. Pass another
path to `--data` if necessary.

## Reproduce training and evaluation

```powershell
python -m ber.data --data ../student_resource/dataset
python -m ber.blocking --anchors 30000 --cap 80
python -m ber.experiment --out artifacts/address_baseline --report reports/address_baseline.json --transfer
python -m ber.cap_study
python -m ber.confirm
python -m unittest discover -s tests -v
```

Preparation reads TSVs explicitly, preserves raw fields, builds additional text
representations, and audits IDs, labels, country agreement, missingness, and
cardinality. See `reports/data_audit.json` for the complete aggregate audit.

Candidate generation searches **every training S2/S3 record**, even though only
30,000 S1 anchors are sampled for this first experiment. It uses full names,
addresses, name prefixes with address numbers, name words, address words, address
word pairs, and address numbers paired with words. Country partitions and bounded
posting lists control the comparison count. At most 80 candidates reach the matcher.
Hashes are used only as internal blocking keys; record IDs are never model features.

CatBoost learns 47 numerical comparison features. Anchors are deterministically
assigned to 60% fitting, 15% early stopping, 15% threshold calibration, and 10%
development holdout partitions. All known positive records of an anchor share its
partition; the audit verifies no positive target belongs to two anchors. Thresholds
maximize the official **entity-level** score, not pair classification accuracy.

Retrieval frequencies use the full **unlabeled search inventory**. Held-out labels
never create candidates. Country-transfer runs fit and calibrate using only one
country's labels, then evaluate the other country. These are stress tests, not
measurements of French accuracy. Repeated development-holdout results should not be
presented as an untouched estimate; keep a separate confirmation sample for final
decisions.

`reports/baseline.json` records the original narrower name-led blocker. Reproducing
that historical run requires its earlier code; the current blocker includes address
retrieval. `reports/address_baseline.json` records the current experiment.

## Generate both submission files

For the first submission, use the selected depth-10 checkpoint and 640-candidate
configuration in `artifacts/submission_v1`. Its independent 5,000-entity confirmation
macro F0.5 is 0.928835. This checkpoint is a local artifact excluded from Git;
`python -m ber.tune` recreates `artifacts/tuned/depth10.cbm` from the documented
development features, and `python -m ber.freeze_first` assembles the selected
checkpoint and configuration. The first full test export is currently running.

```powershell
$env:PYTHONPATH='src'
python -m ber.predict --model artifacts/submission_v1 --out output/submission_v1 --batch-size 10000 --query-batches 1
python -m ber.validate --output output/submission_v1
python ../student_resource/utils/validate_submission.py --matching output/submission_v1/matching_results.tsv --test-dir ../student_resource/dataset/test
```

`matching_results.tsv` is the leaderboard upload. The final archive also needs
`candidate_pairs.tsv`. The official README states that public and private scores
use different portions of this same complete test submission.

`python tools/finish_submission.py` resumes the same export, runs the streaming
subset/coverage validator and the supplied official formatter, then writes
`output/submission_v1/completion.json` with `PASS` and output checksums. It requires
the optional native feature extension; use the direct `ber.predict` command above
for the pure Python path. Neither command uploads to the leaderboard.

An optional native implementation of the same 47 features is in
`src/ber/fast_features.cpp`. On Windows with Python 3.12 and MinGW g++, run
`tools/build_fast_features.ps1`, then set `$env:BER_FAST_FEATURES='1'` before
inference. On 16,000 supplied-text comparisons all feature values matched the
Python path exactly, and a 10,000-anchor export produced byte-identical output.
The pipeline defaults to Python if the native option is not selected.

The historical baseline commands follow for reproducing older measurements.

```powershell
python -m ber.predict --model artifacts/address_baseline --out output/baseline
python -m ber.validate --output output/baseline
python ../student_resource/utils/validate_submission.py --matching output/baseline/matching_results.tsv --test-dir ../student_resource/dataset/test --check-ids
```

Inference builds the test retrieval index, processes bounded batches, and saves
checksummed shards. Re-running the same command resumes completed shards. A changed
model/configuration requires a new output directory. The exported candidate file
contains exactly the candidates the matcher scored; predictions are always subsets.
Every test S1 anchor gets a row, including France and empty predictions.

The supplied validator holds all candidate lists in memory; its full-dataset
candidate check can exceed laptop RAM. The pipeline also includes a streaming
validator for full exports. On sufficient RAM, add `--check-ids` to the official
validator for explicit target-ID checks. Do not submit a run made with `--limit`:
that option is only for local smoke tests.

An earlier throughput experiment used a cheap lexical shortlist after the 80-candidate retrieval
union. It retains complementary name, address, and combined rankings, up to 30 rows
per anchor (median 21 on confirmation). That historical budget was selected on calibration data
within 0.002 macro F0.5 of the best tested budget. The exact final shortlist, not the
larger retrieval union, is what `candidate_pairs.tsv` exports. To run the unpruned
80-candidate model, use a separate model directory with `shortlist_cap` set to 80 and
a new output folder. Default inference uses four worker processes; `--workers 1`
reduces memory and CPU use. Workers change throughput, not the selected candidates.

## Quality experiments

The broader study searches up to 640 candidates and evaluates the actual matching
score, including new false positives. Use the existing 30,000-anchor experiment:

```powershell
python -m ber.retrieval_study
python -m ber.wide_evaluate
python -m ber.tune
```

For the multilingual feature experiment, create a separate GPU environment and
install `requirements-gpu.txt`. The pinned model revision and verified MIT license
are recorded in `reports/pretrained_model.json`. Downloading that checkpoint does
not download an external matching dataset.

```powershell
python -m venv .venv-gpu
.\.venv-gpu\Scripts\Activate.ps1
python -m pip install -r requirements-gpu.txt
python -m pip install -e .
python -m ber.download_model
python -m ber.semantic --field name --max-length 512
python -m ber.semantic_train --fields name
```

The encoder runs locally on raw supplied text. Its frozen multilingual vectors add
similarity features to a classifier trained only on challenge labels. These scripts
are experiments; the production inference path must use the selected model's exact
feature schema. A neural experiment is not automatically promoted to production.

## Working files and limits

- `src/ber/`: preparation, retrieval, feature extraction, training, scoring, inference.
- `tests/`: official metric edge cases and comparison-feature invariants.
- `reports/`: aggregate statistics and measured experiments, safe to version.
- `artifacts/`: local databases, learned models, features, and diagnostic record IDs.
- `output/`: local submission files and resumable shards.

Dataset TSVs, PDFs, archives, local artifacts, model binaries, and predictions are
ignored by Git. If input files change, use a new database/artifact directory; cached
tables must not be reused across different datasets. Never infer identities through
external databases or APIs. This baseline has no such calls and spends no AWS credit.
