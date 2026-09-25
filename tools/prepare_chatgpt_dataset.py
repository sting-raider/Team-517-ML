"""Prepare the complete challenge dataset for a shared ChatGPT Project.

Splits TSV files losslessly at row boundaries so every shard remains a valid TSV
with the original header. The raw challenge files are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


DEFAULT_TARGET_MIB = 44
DEFAULT_MAX_FILES = 25


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def split_tsv(source: Path, out_dir: Path, target_bytes: int) -> list[dict]:
    rel_stem = "__".join(source.with_suffix("").parts)
    shards: list[dict] = []

    with source.open("rb") as src:
        header = src.readline()
        if not header:
            raise ValueError(f"Empty TSV: {source}")

        part = 1
        out = None
        out_path = None
        rows = 0
        payload_bytes = 0

        def close_current():
            nonlocal out, out_path, rows, payload_bytes
            if out is None or out_path is None:
                return
            out.close()
            shards.append(
                {
                    "original": str(source),
                    "shard": out_path.name,
                    "rows": rows,
                    "bytes": out_path.stat().st_size,
                    "sha256": sha256(out_path),
                }
            )
            out = None
            out_path = None
            rows = 0
            payload_bytes = 0

        for line in src:
            if out is None:
                out_path = out_dir / f"{rel_stem}__part{part:02d}.tsv"
                out = out_path.open("wb")
                out.write(header)
                payload_bytes = len(header)

            # Split before the next row if adding it would cross the target.
            if rows > 0 and payload_bytes + len(line) > target_bytes:
                close_current()
                part += 1
                out_path = out_dir / f"{rel_stem}__part{part:02d}.tsv"
                out = out_path.open("wb")
                out.write(header)
                payload_bytes = len(header)

            out.write(line)
            rows += 1
            payload_bytes += len(line)

        close_current()

    return shards


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True,
                        help="Path to student_resource/dataset")
    parser.add_argument("--out", type=Path, default=Path("chatgpt_dataset"))
    parser.add_argument("--target-mib", type=float, default=DEFAULT_TARGET_MIB,
                        help="Target maximum shard size in MiB (default: 44)")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES,
                        help="Maximum TSV shard count allowed (default: 25)")
    args = parser.parse_args()

    data = args.data.resolve()
    out = args.out.resolve()
    if not data.exists():
        raise FileNotFoundError(data)
    if args.target_mib <= 0:
        raise ValueError("--target-mib must be positive")
    if args.max_files <= 0:
        raise ValueError("--max-files must be positive")

    files = sorted(data.rglob("*.tsv"))
    if not files:
        raise FileNotFoundError(f"No TSV files found under {data}")

    out.mkdir(parents=True, exist_ok=True)
    existing = list(out.glob("*.tsv"))
    if existing:
        raise FileExistsError(
            f"{out} already contains TSV shards. Use an empty output directory."
        )

    target_bytes = int(args.target_mib * 1024 * 1024)
    manifest: dict = {
        "source_root": str(data),
        "target_mib": args.target_mib,
        "max_files": args.max_files,
        "sources": [],
        "shards": [],
    }

    for source in files:
        rel = source.relative_to(data)
        produced = split_tsv(source, out, target_bytes)
        for item in produced:
            item["original"] = str(rel)
        manifest["sources"].append(
            {
                "path": str(rel),
                "bytes": source.stat().st_size,
                "sha256": sha256(source),
                "shards": len(produced),
            }
        )
        manifest["shards"].extend(produced)

    manifest["shard_count"] = len(manifest["shards"])
    manifest["total_source_bytes"] = sum(x["bytes"] for x in manifest["sources"])
    manifest["total_shard_bytes"] = sum(x["bytes"] for x in manifest["shards"])

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Prepared {manifest['shard_count']} TSV shards in {out}")
    print(f"Manifest: {manifest_path}")
    for src in manifest["sources"]:
        print(f"  {src['path']}: {src['shards']} shard(s)")

    if manifest["shard_count"] > args.max_files:
        raise RuntimeError(
            f"Produced {manifest['shard_count']} shards, above --max-files "
            f"{args.max_files}. Re-run into an empty directory with a slightly "
            "larger --target-mib, while staying below the upload limit."
        )

    print("PASS: complete dataset fits the configured Project file budget.")


if __name__ == "__main__":
    main()
