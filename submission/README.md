# Team 517 business entity resolution pipeline

This code regenerates both final outputs from the challenge's supplied TSV files. It uses no external entity database, geocoder, business search, or record-ID signal. The only downloads made during training are the pinned, permitted pretrained multilingual checkpoints described in `Documentation_template.md` and the checked-in INT005/M017 reports. The final candidate set contains at most 32 Source 2/3 records per Source 1 business.

## Inputs and environment

Use Python 3.12 and a Modal account with a GPU-enabled workspace. Place the organizer's `student_resource/dataset/{train,test}/` folder next to this `business_entity_resolution` directory. The expected local layout is:

```
code/
├── business_entity_resolution/
│   ├── src/ber/
│   ├── tools/stage_modal.py
│   ├── modal_*.py
│   ├── pyproject.toml
│   └── requirements.txt
└── student_resource/dataset/
```

Install `requirements.txt` and the local package. The Modal scripts install the
additional pinned GPU packages inside their Linux images; those versions are
also listed in `requirements-gpu.txt`. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
```

Modal must be authenticated (`modal token new`, if no token is configured). Modal images in the checked-in scripts independently pin their runtime dependencies. The volume name is `team517-business-er`; choose a new workspace or clear an old run's volume if reproducing from scratch so checkpoints from another experiment cannot be reused accidentally.

## Rebuild from supplied data and training labels

The baseline CatBoost is needed only to reproduce the historical hard-negative mining and later ensemble. Create it and the indexed DuckDB database locally:

```powershell
python -m ber.data --data ../student_resource/dataset --db artifacts/data.duckdb --report reports/data_audit.json
python -m ber.blocking --db artifacts/data.duckdb --anchors 30000 --cap 80
python -m ber.experiment --db artifacts/data.duckdb --out artifacts/submission_v1 --report reports/submission_v1.json
python tools/stage_modal.py --database --model
```

Then train the 53-feature and 57-feature CatBoost stages, the learned retrieval encoder, and the multilingual pair reranker on the supplied *training* labels:

```powershell
modal run modal_v2.py --action train --depth 10
modal run modal_v3.py --action train --depth 10
modal run modal_dense.py
modal run modal_crossencoder.py
```

`modal_v2.py` and `modal_v3.py` are prerequisites for the final CatBoost features and neural hard-negative sampling. Model weights and intermediate databases are private Modal volume artifacts, never included in the submission zip. Encoder and reranker training code pins the pretrained model revisions and their MIT/Apache-2.0 licenses; each checkpoint is around 118 million parameters, well below the 8-billion limit.

Build the full country-sharded ANN indexes on *all* supplied test Source 2/3 records, then score every test Source 1 record. The 16 nearest neural records plus top lexical/character records form a frozen set of at most 32 candidates per anchor. Pair scoring does not add candidates. The final CPU pass restores exact-name matches where the target address is empty and the anchor's normalized name is unique in its country.

```powershell
modal run modal_dense_test.py
modal run modal_neural_submission.py --threshold 0.95 --dense-prior -2 --parts-per-country 4
modal run modal_recover_blank.py
```

The matching file is `project/output/submission_v6_blank_recovery/matching_results.tsv` in the Modal volume. Its paired **unchanged** blocker artifact is `project/output/submission_v5_neural32/candidate_pairs.tsv`. Download both to `output/matching_results.tsv` and `output/candidate_pairs.tsv` respectively. Their expected SHA-256 digests for this run are:

```
matching_results.tsv  ab1b41964cdfbbccb4956c47d362d6c9b08cf7de73d67c3c8b66a963f61010e5
candidate_pairs.tsv  fa286e237b9bdd31905f901d2a1449771698249d4c1dfe45dcbfa38bf647c3ec
```

The recovery code selects only from the frozen blocker output, so every predicted target is a candidate. Run the organizer's `student_resource/utils/validate_submission.py` with `--matching` and `--candidate` after downloading. The 1,732,544-row matching output has already passed its organizer format check. The development protocol and limitations, including the unlabeled French test slice, are detailed in `Documentation_template.md`.
