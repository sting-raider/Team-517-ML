"""Modal compute for Team 517; challenge data and outputs live only in a private Volume."""
import json
import re
from pathlib import Path

import modal

ROOT = Path(__file__).parent
VOLUME_NAME = "team517-business-er"
VOLUME_ROOT = Path("/volume")
SCRATCH = Path("/tmp/team517")

app = modal.App("team517-business-er")
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("g++", "git")
    .pip_install_from_requirements(str(ROOT / "requirements.txt"))
    .env({"PYTHONPATH": "/app/src"})
    .add_local_dir(str(ROOT / "src"), "/app/src")
    .add_local_dir(str(ROOT / "tests"), "/app/tests")
)


@app.function(image=image, cpu=2, memory=4096, timeout=900)
def smoke():
    import subprocess
    import sys

    command = [sys.executable, "-m", "unittest", "discover", "-s", "/app/tests", "-v"]
    subprocess.run(command, check=True)
    from ber.features import FEATURE_NAMES
    return {"status": "PASS", "feature_count": len(FEATURE_NAMES)}


def _run(module, *args):
    import subprocess
    import sys

    subprocess.run([sys.executable, "-u", "-m", module, *map(str, args)], cwd=SCRATCH, check=True)


def _enable_native_features():
    """Compile the checked-in C++ feature implementation in the remote container."""
    import os
    import shutil
    import subprocess
    import sys
    import sysconfig

    source_root = SCRATCH / "src"
    shutil.copytree("/app/src/ber", source_root / "ber", dirs_exist_ok=True)
    headers = SCRATCH / "rapidfuzz-cpp"
    subprocess.run(["git", "clone", "--depth", "1", "--branch", "v3.3.3",
                    "https://github.com/rapidfuzz/rapidfuzz-cpp.git", str(headers)], check=True)
    extension = source_root / "ber" / ("_fast_features" + sysconfig.get_config_var("EXT_SUFFIX"))
    subprocess.run(["g++", "-O3", "-std=c++17", "-shared", "-fPIC",
                    "-I" + sysconfig.get_paths()["include"], "-I" + str(headers),
                    str(source_root / "ber/fast_features.cpp"), "-o", str(extension)], check=True)
    sys.path.insert(0, str(source_root))
    os.environ["BER_FAST_FEATURES"] = "1"


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8, memory=32768,
              timeout=4 * 60 * 60)
def prepare_database():
    """Build the database and both indexes from uploaded challenge TSV files."""
    import shutil
    import zipfile
    from ber.blocking import build_index
    from ber.data import connect

    dataset = VOLUME_ROOT / "dataset"
    if not (dataset / "test/test_source1.tsv").exists():
        archive = dataset / "source.zip"
        if not archive.exists():
            raise FileNotFoundError("Stage the supplied archive with tools/stage_modal.py --archive")
        extracted = SCRATCH / "dataset"
        with zipfile.ZipFile(archive) as bundle:
            for split in ("train", "test"):
                for source in (1, 2, 3):
                    name = f"{split}_source{source}.tsv"
                    member = f"student_resource/dataset/{split}/{name}"
                    destination = extracted / split / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as original, destination.open("wb") as copy:
                        shutil.copyfileobj(original, copy)
            member = "student_resource/dataset/train/train_ground_truth.tsv"
            destination = extracted / "train/train_ground_truth.tsv"
            with bundle.open(member) as original, destination.open("wb") as copy:
                shutil.copyfileobj(original, copy)
        dataset = extracted
    (SCRATCH / "artifacts").mkdir(parents=True, exist_ok=True)
    (SCRATCH / "reports").mkdir(parents=True, exist_ok=True)
    db = SCRATCH / "artifacts/data.duckdb"
    _run("ber.data", "--data", dataset, "--db", db,
         "--report", SCRATCH / "reports/data_audit.json")
    con = connect(db)
    for split in ("train", "test"):
        build_index(con, split)
    con.close()
    destination = VOLUME_ROOT / "project/artifacts"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db, destination / "data.duckdb")
    reports = VOLUME_ROOT / "project/reports"
    reports.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRATCH / "reports/data_audit.json", reports / "data_audit.json")
    volume.commit()
    return {"status": "PASS", "database_bytes": db.stat().st_size}


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8, memory=32768,
              timeout=4 * 60 * 60)
def train_catboost():
    """Run the existing tuned CatBoost experiment using uploaded feature arrays."""
    import shutil

    source = VOLUME_ROOT / "project/artifacts"
    needed = (
        "address_baseline/features.npz", "address_baseline/anchors.json",
        "wide_calibration/features.npz", "wide_calibration/anchors.json",
    )
    missing = [name for name in needed if not (source / name).exists()]
    if missing:
        raise FileNotFoundError(f"Stage training inputs with tools/stage_modal.py --training: {missing}")
    for name in needed:
        destination = SCRATCH / "artifacts" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, destination)
    (SCRATCH / "reports").mkdir(parents=True, exist_ok=True)
    _run("ber.tune")
    _run("ber.freeze_first")
    for folder in ("tuned", "submission_v1"):
        shutil.copytree(SCRATCH / "artifacts" / folder, source / folder, dirs_exist_ok=True)
    reports = VOLUME_ROOT / "project/reports"
    reports.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRATCH / "reports/tuning.json", reports / "tuning.json")
    volume.commit()
    return {"status": "PASS", "calibration": json.loads((reports / "tuning.json").read_text())["depth10"]["macro_f0_5"]}


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=8, memory=32768,
              timeout=4 * 60 * 60)
def score_test(run_name: str = "modal_v1", workers: int = 8, candidate_cap: int = 160,
               partition_index: int = 0, partition_count: int = 1):
    """Score all test anchors; export both official TSVs into the Modal Volume."""
    import shutil
    import threading
    _enable_native_features()
    from ber.predict import predict, sha256
    from ber.validate import validate

    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", run_name):
        raise ValueError("run_name must be 1-48 letters, digits, underscores, or hyphens")
    if not 1 <= workers <= 12:
        raise ValueError("workers must be between 1 and 12")
    if not 1 <= candidate_cap <= 640:
        raise ValueError("candidate_cap must be between 1 and 640")
    if not 1 <= partition_count <= 16 or not 0 <= partition_index < partition_count:
        raise ValueError("Invalid partition index/count")
    source = VOLUME_ROOT / "project/artifacts"
    db_source = source / "data.duckdb"
    model_source = source / "submission_v1"
    if not db_source.exists() or not (model_source / "mixed.cbm").exists():
        raise FileNotFoundError("Stage the database and model with tools/stage_modal.py")
    (SCRATCH / "artifacts").mkdir(parents=True, exist_ok=True)
    db = SCRATCH / "artifacts/data.duckdb"
    shutil.copy2(db_source, db)
    model_dir = SCRATCH / "artifacts/submission_v1"
    shutil.copytree(model_source, model_dir, dirs_exist_ok=True)
    if candidate_cap != 640:
        study_path = VOLUME_ROOT / "project/reports/candidate_budget.json"
        if not study_path.exists():
            raise FileNotFoundError("Stage reports/candidate_budget.json with tools/stage_modal.py --model")
        study = json.loads(study_path.read_text(encoding="utf-8"))
        config_path = model_dir / "model_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["threshold"] = study["caps"][str(candidate_cap)]["threshold"]
        config["candidate_cap"] = candidate_cap
        config["shortlist_cap"] = candidate_cap
        config["selection"] = "calibrated smaller candidate budget under organizer ranking rule"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    out = VOLUME_ROOT / "project/output" / run_name
    stop = threading.Event()

    def checkpoint():
        while not stop.wait(300):
            volume.commit()

    writer = threading.Thread(target=checkpoint, daemon=True)
    writer.start()
    try:
        predict(db, model_dir, out, batch_size=10000, cap=candidate_cap,
                workers=workers, query_batches=1, partition_index=partition_index,
                partition_count=partition_count, profile_path=out / "profile.json")
        checked = validate(db, out, check_ids=False) if partition_count == 1 else None
        result = {"status": "PASS", "candidate_cap": candidate_cap,
                  "partition_index": partition_index, "partition_count": partition_count,
                  "validation": checked,
                  "matching_sha256": sha256(out / "matching_results.tsv"),
                  "candidate_sha256": sha256(out / "candidate_pairs.tsv")}
        (out / "completion.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        stop.set()
        writer.join(timeout=30)
        volume.commit()


@app.function(image=image, volumes={str(VOLUME_ROOT): volume}, cpu=4, memory=16384,
              timeout=60 * 60)
def merge_score(run_name: str, partition_count: int, candidate_cap: int):
    """Stream sorted partition outputs into one complete, validated submission."""
    import heapq
    import shutil
    from contextlib import ExitStack
    from ber.predict import sha256
    from ber.validate import validate

    out = VOLUME_ROOT / "project/output" / run_name
    out.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for filename in ("matching_results.tsv", "candidate_pairs.tsv"):
            streams = []
            for index in range(partition_count):
                part = VOLUME_ROOT / "project/output" / f"{run_name}_part{index}of{partition_count}"
                streams.append(stack.enter_context((part / filename).open(encoding="utf-8", newline="")))
            headers = [stream.readline() for stream in streams]
            if len(set(headers)) != 1:
                raise ValueError(f"Partition headers disagree for {filename}")
            with (out / (filename + ".tmp")).open("w", encoding="utf-8", newline="") as dest:
                dest.write(headers[0])
                heap = []
                for index, stream in enumerate(streams):
                    if line := stream.readline():
                        heapq.heappush(heap, (line.split("\t", 1)[0], index, line))
                while heap:
                    _, index, line = heapq.heappop(heap)
                    dest.write(line)
                    if next_line := streams[index].readline():
                        heapq.heappush(heap, (next_line.split("\t", 1)[0], index, next_line))
            (out / (filename + ".tmp")).replace(out / filename)
    db = SCRATCH / "artifacts/data.duckdb"
    db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VOLUME_ROOT / "project/artifacts/data.duckdb", db)
    checked = validate(db, out, check_ids=False)
    result = {"status": "PASS", "candidate_cap": candidate_cap,
              "partition_count": partition_count, "validation": checked,
              "matching_sha256": sha256(out / "matching_results.tsv"),
              "candidate_sha256": sha256(out / "candidate_pairs.tsv")}
    (out / "completion.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    volume.commit()
    return result


@app.local_entrypoint()
def main(action: str = "smoke", run_name: str = "modal_v1", workers: int = 8,
         candidate_cap: int = 160, partitions: int = 8):
    actions = {"smoke": smoke, "prepare": prepare_database,
               "train": train_catboost, "score": score_test}
    if action == "parallel-score":
        if not 2 <= partitions <= 16:
            raise ValueError("partitions must be between 2 and 16")
        calls = [score_test.spawn(run_name=f"{run_name}_part{i}of{partitions}",
                                  workers=workers, candidate_cap=candidate_cap,
                                  partition_index=i, partition_count=partitions)
                 for i in range(partitions)]
        for i, call in enumerate(calls):
            print(f"Partition {i}: {call.get()}", flush=True)
        result = merge_score.remote(run_name, partitions, candidate_cap)
    elif action == "score":
        result = score_test.remote(run_name=run_name, workers=workers, candidate_cap=candidate_cap)
    else:
        if action not in actions:
            raise ValueError(f"Unknown action: {action}. Choose one of {', '.join(actions)}, parallel-score")
        result = actions[action].remote()
    print(json.dumps(result, indent=2))
