"""Portable candidate-cache export/import keyed by stable entity IDs.

The runtime blocker stores target ``rowid`` values because joins are fast. Those
rowids are database-local implementation details, so they must not be used as a
shared experiment artifact. This module writes a deterministic gzip CSV using
stable entity IDs plus a checksummed JSON manifest, then resolves IDs back to the
current database rowids on import.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
from pathlib import Path

SCHEMA_VERSION = 1
COLUMNS = ["anchor", "target", "retrieval", "hits", "source", "rank"]
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(value: str) -> str:
    if not _IDENT.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def _manifest_path(path: Path) -> Path:
    return path.with_name(path.name + ".manifest.json")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json_atomic(path: Path, payload: dict) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def export_candidate_cache(
    connection,
    path: Path,
    *,
    split: str,
    anchor_table: str,
    candidate_table: str,
    candidate_cap: int,
    provenance: dict | None = None,
    batch_size: int = 50000,
) -> dict:
    """Export a candidate table to a deterministic stable-ID cache.

    ``candidate_table`` must use the repository's canonical columns
    ``anchor,rid,retrieval,hits``. ``rid`` is resolved through ``split`` only for
    export; it never appears in the portable file.
    """
    if candidate_cap < 1:
        raise ValueError("candidate_cap must be positive")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    split = _ident(split)
    anchor_table = _ident(anchor_table)
    candidate_table = _ident(candidate_table)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")

    candidate_rows = connection.execute(f"SELECT count(*) FROM {candidate_table}").fetchone()[0]
    unknown_anchors = connection.execute(
        f"""SELECT count(*) FROM {candidate_table} p
        WHERE NOT EXISTS (SELECT 1 FROM {anchor_table} a WHERE a.entity_id=p.anchor)"""
    ).fetchone()[0]
    if unknown_anchors:
        raise ValueError(f"Candidate table contains {unknown_anchors} rows with unknown anchors")
    unknown_targets = connection.execute(
        f"""SELECT count(*) FROM {candidate_table} p
        WHERE NOT EXISTS (SELECT 1 FROM {split} r WHERE r.rowid=p.rid AND r.source IN (2,3))"""
    ).fetchone()[0]
    if unknown_targets:
        raise ValueError(f"Candidate table contains {unknown_targets} invalid target rowids")

    sql = f"""SELECT p.anchor,r.entity_id,p.retrieval,p.hits,r.source
        FROM {candidate_table} p
        JOIN {split} r ON p.rid=r.rowid
        JOIN {anchor_table} a ON p.anchor=a.entity_id
        ORDER BY p.anchor,p.retrieval DESC,r.entity_id"""
    cursor = connection.execute(sql)
    row_count = anchor_count = max_rank = 0
    current_anchor = None
    rank = 0
    targets = set()
    with gzip.open(temp, "wt", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for anchor, target, retrieval, hits, source in rows:
                anchor, target = str(anchor), str(target)
                if anchor != current_anchor:
                    current_anchor = anchor
                    anchor_count += 1
                    rank = 1
                    targets = set()
                else:
                    rank += 1
                if target in targets:
                    raise ValueError(f"Duplicate candidate pair: {anchor}/{target}")
                targets.add(target)
                if rank > candidate_cap:
                    raise ValueError(
                        f"Candidate table exceeds declared cap {candidate_cap}: {anchor} rank {rank}"
                    )
                retrieval = float(retrieval)
                if not math.isfinite(retrieval):
                    raise ValueError(f"Non-finite retrieval score for {anchor}/{target}")
                hits, source = int(hits), int(source)
                if hits < 1 or source not in (2, 3):
                    raise ValueError(f"Invalid candidate metadata for {anchor}/{target}")
                writer.writerow([anchor, target, format(retrieval, ".17g"), hits, source, rank])
                row_count += 1
                max_rank = max(max_rank, rank)
    if row_count != candidate_rows:
        temp.unlink(missing_ok=True)
        raise ValueError(f"Candidate export changed row count: expected {candidate_rows}, got {row_count}")
    temp.replace(path)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": "gzip_csv",
        "columns": COLUMNS,
        "split": split,
        "candidate_cap": int(candidate_cap),
        "row_count": row_count,
        "anchor_count": anchor_count,
        "max_rank": max_rank,
        "sha256": _sha256(path),
        "provenance": provenance or {},
    }
    _write_json_atomic(_manifest_path(path), manifest)
    return manifest


def _load_manifest(path: Path) -> dict:
    mpath = _manifest_path(path)
    if not path.exists() or not mpath.exists():
        raise ValueError(f"Candidate cache or manifest missing: {path}")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported candidate cache schema: {manifest.get('schema_version')}")
    if manifest.get("format") != "gzip_csv" or manifest.get("columns") != COLUMNS:
        raise ValueError("Candidate cache manifest schema mismatch")
    digest = _sha256(path)
    if digest != manifest.get("sha256"):
        raise ValueError("Candidate cache checksum mismatch")
    return manifest


def _validated_rows(path: Path, manifest: dict):
    row_count = anchor_count = max_rank = 0
    previous_anchor = None
    current_anchor = None
    expected_rank = 0
    targets = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"Candidate cache header mismatch: {reader.fieldnames}")
        for row in reader:
            anchor, target = row["anchor"], row["target"]
            if not anchor or not target:
                raise ValueError("Candidate cache contains an empty anchor or target")
            if anchor != current_anchor:
                if previous_anchor is not None and anchor <= previous_anchor:
                    raise ValueError("Candidate cache anchors are not strictly sorted/grouped")
                previous_anchor = anchor
                current_anchor = anchor
                expected_rank = 1
                targets = set()
                anchor_count += 1
            else:
                expected_rank += 1
            try:
                retrieval = float(row["retrieval"])
                hits = int(row["hits"])
                source = int(row["source"])
                rank = int(row["rank"])
            except (TypeError, ValueError) as e:
                raise ValueError(f"Invalid candidate row types for {anchor}/{target}") from e
            if not math.isfinite(retrieval):
                raise ValueError(f"Non-finite retrieval score for {anchor}/{target}")
            if hits < 1 or source not in (2, 3):
                raise ValueError(f"Invalid candidate metadata for {anchor}/{target}")
            if rank != expected_rank:
                raise ValueError(f"Non-contiguous rank for {anchor}: expected {expected_rank}, got {rank}")
            if target in targets:
                raise ValueError(f"Duplicate candidate pair: {anchor}/{target}")
            targets.add(target)
            if rank > manifest["candidate_cap"]:
                raise ValueError(f"Candidate rank exceeds manifest cap for {anchor}")
            row_count += 1
            max_rank = max(max_rank, rank)
            yield anchor, target, retrieval, hits, source, rank
    expected = (manifest.get("row_count"), manifest.get("anchor_count"), manifest.get("max_rank"))
    actual = (row_count, anchor_count, max_rank)
    if actual != expected:
        raise ValueError(f"Candidate cache manifest counts mismatch: expected {expected}, got {actual}")


def validate_candidate_cache(
    path: Path,
    *,
    expected_split: str | None = None,
    expected_cap: int | None = None,
) -> dict:
    path = Path(path)
    manifest = _load_manifest(path)
    if expected_split is not None and manifest["split"] != expected_split:
        raise ValueError(f"Candidate cache split mismatch: {manifest['split']} != {expected_split}")
    if expected_cap is not None and manifest["candidate_cap"] != expected_cap:
        raise ValueError(f"Candidate cache cap mismatch: {manifest['candidate_cap']} != {expected_cap}")
    for _ in _validated_rows(path, manifest):
        pass
    return manifest


def import_candidate_cache(
    connection,
    path: Path,
    *,
    anchor_table: str,
    result_table: str,
    expected_split: str | None = None,
    expected_cap: int | None = None,
    batch_size: int = 50000,
) -> dict:
    """Import a stable-ID cache and resolve targets to current database rowids."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    path = Path(path)
    manifest = _load_manifest(path)
    split = _ident(manifest["split"])
    if expected_split is not None and split != expected_split:
        raise ValueError(f"Candidate cache split mismatch: {split} != {expected_split}")
    if expected_cap is not None and manifest["candidate_cap"] != expected_cap:
        raise ValueError(f"Candidate cache cap mismatch: {manifest['candidate_cap']} != {expected_cap}")
    anchor_table = _ident(anchor_table)
    result_table = _ident(result_table)
    staging = _ident(f"_{result_table}_cache_staging")

    connection.execute(f"DROP TABLE IF EXISTS {staging}")
    is_duckdb = "duckdb" in connection.__class__.__module__.lower()
    try:
        if is_duckdb:
            for _ in _validated_rows(path, manifest):
                pass
            connection.execute(
                f"""CREATE TEMP TABLE {staging} AS SELECT
                anchor::VARCHAR AS anchor,target::VARCHAR AS target,
                retrieval::REAL AS retrieval,hits::SMALLINT AS hits,
                source::TINYINT AS source,rank::INTEGER AS rank
                FROM read_csv(?, delim=',', header=true, all_varchar=true)""",
                [str(path.resolve())],
            )
        else:
            connection.execute(
                f"CREATE TEMP TABLE {staging} (anchor VARCHAR,target VARCHAR,retrieval REAL,hits SMALLINT,source TINYINT,rank INTEGER)"
            )
            batch = []
            for row in _validated_rows(path, manifest):
                batch.append(row)
                if len(batch) >= batch_size:
                    connection.executemany(f"INSERT INTO {staging} VALUES (?,?,?,?,?,?)", batch)
                    batch.clear()
            if batch:
                connection.executemany(f"INSERT INTO {staging} VALUES (?,?,?,?,?,?)", batch)

        unknown_anchors = connection.execute(
            f"""SELECT count(DISTINCT s.anchor) FROM {staging} s
            WHERE NOT EXISTS (SELECT 1 FROM {anchor_table} a WHERE a.entity_id=s.anchor)"""
        ).fetchone()[0]
        if unknown_anchors:
            raise ValueError(f"Candidate cache contains {unknown_anchors} unknown anchors")
        unknown_targets = connection.execute(
            f"""SELECT count(*) FROM {staging} s
            WHERE NOT EXISTS (SELECT 1 FROM {split} t WHERE t.entity_id=s.target AND t.source=s.source)"""
        ).fetchone()[0]
        if unknown_targets:
            raise ValueError(f"Candidate cache contains {unknown_targets} unknown/source-mismatched targets")

        connection.execute(f"DROP TABLE IF EXISTS {result_table}")
        connection.execute(
            f"""CREATE TABLE {result_table} AS
            SELECT s.anchor,t.rowid AS rid,s.retrieval,s.hits
            FROM {staging} s
            JOIN {split} t ON t.entity_id=s.target AND t.source=s.source
            JOIN {anchor_table} a ON a.entity_id=s.anchor
            ORDER BY s.anchor,s.rank"""
        )
        imported = connection.execute(f"SELECT count(*) FROM {result_table}").fetchone()[0]
        if imported != manifest["row_count"]:
            connection.execute(f"DROP TABLE {result_table}")
            raise ValueError(
                f"Candidate cache import changed row count: expected {manifest['row_count']}, got {imported}"
            )
    finally:
        connection.execute(f"DROP TABLE IF EXISTS {staging}")
    return manifest


def main():
    from .data import connect

    p = argparse.ArgumentParser(description="Export/import portable stable-ID candidate caches")
    p.add_argument("--db", type=Path, default=Path("artifacts/data.duckdb"))
    sub = p.add_subparsers(dest="command", required=True)

    e = sub.add_parser("export")
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--split", choices=["train", "test"], required=True)
    e.add_argument("--anchors", required=True)
    e.add_argument("--candidates", required=True)
    e.add_argument("--cap", type=int, required=True)
    e.add_argument("--provenance-json")

    i = sub.add_parser("import")
    i.add_argument("--input", type=Path, required=True)
    i.add_argument("--anchors", required=True)
    i.add_argument("--result", required=True)
    i.add_argument("--expected-split", choices=["train", "test"])
    i.add_argument("--expected-cap", type=int)

    v = sub.add_parser("validate")
    v.add_argument("--input", type=Path, required=True)
    v.add_argument("--expected-split", choices=["train", "test"])
    v.add_argument("--expected-cap", type=int)

    a = p.parse_args()
    if a.command == "validate":
        print(json.dumps(validate_candidate_cache(
            a.input, expected_split=a.expected_split, expected_cap=a.expected_cap
        ), indent=2))
        return
    c = connect(a.db)
    try:
        if a.command == "export":
            provenance = json.loads(a.provenance_json) if a.provenance_json else {}
            result = export_candidate_cache(
                c, a.out, split=a.split, anchor_table=a.anchors,
                candidate_table=a.candidates, candidate_cap=a.cap, provenance=provenance,
            )
        else:
            result = import_candidate_cache(
                c, a.input, anchor_table=a.anchors, result_table=a.result,
                expected_split=a.expected_split, expected_cap=a.expected_cap,
            )
    finally:
        c.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
