"""Upload an explicit allowlist of challenge inputs to the private Team 517 Volume."""
import argparse
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
VOLUME_NAME = "team517-business-er"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", action="store_true", help="Upload the local DuckDB data/index cache")
    parser.add_argument("--training", action="store_true", help="Upload precomputed labeled feature arrays")
    parser.add_argument("--model", action="store_true", help="Upload the selected checkpoint and configuration")
    parser.add_argument("--dataset", action="store_true", help="Upload supplied train and test TSVs for remote database preparation")
    parser.add_argument("--archive", action="store_true", help="Upload the supplied ZIP for remote database preparation")
    args = parser.parse_args()
    files = []
    if args.database:
        files.append((ROOT / "artifacts/data.duckdb", "/project/artifacts/data.duckdb"))
    if args.training:
        for folder in ("address_baseline", "wide_calibration"):
            for name in ("features.npz", "anchors.json"):
                files.append((ROOT / "artifacts" / folder / name,
                              f"/project/artifacts/{folder}/{name}"))
    if args.model:
        for name in ("mixed.cbm", "model_config.json", "anchors.json"):
            files.append((ROOT / "artifacts/submission_v1" / name,
                          f"/project/artifacts/submission_v1/{name}"))
        budget = ROOT / "reports/candidate_budget.json"
        if budget.is_file():
            files.append((budget, "/project/reports/candidate_budget.json"))
    if args.archive:
        files.append((ROOT.parent / "6ab10eb3b23ba_student_resource.zip", "/dataset/source.zip"))
    if args.dataset:
        for split in ("train", "test"):
            for source in (1, 2, 3):
                name = f"{split}_source{source}.tsv"
                files.append((ROOT.parent / "student_resource/dataset" / split / name,
                              f"/dataset/{split}/{name}"))
        files.append((ROOT.parent / "student_resource/dataset/train/train_ground_truth.tsv",
                      "/dataset/train/train_ground_truth.tsv"))
    if not files:
        parser.error("Choose at least one of --database, --training, --model, --dataset, --archive")
    for local, remote in files:
        if not local.is_file():
            raise FileNotFoundError(local)
        print(f"Stage {local.name}: {local.stat().st_size:,} bytes -> {remote}", flush=True)
    volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
    with volume.batch_upload(force=True) as upload:
        for local, remote in files:
            upload.put_file(str(local), remote)
    print(f"Staged {len(files)} approved input files; no PDFs were uploaded.")


if __name__ == "__main__":
    main()
