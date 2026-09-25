"""Paired entity-bootstrap utilities for comparing per-anchor metrics.

The bootstrap unit is always the Source-1 entity.  This module deliberately
operates on already-computed per-anchor scores so it cannot change matching,
thresholding, candidate generation, or holdout membership.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Mapping

import numpy as np


def _validate_scores(name: str, scores: Mapping[str, float]) -> dict[str, float]:
    if not scores:
        raise ValueError(f"{name} score mapping is empty")
    out: dict[str, float] = {}
    for anchor, value in scores.items():
        key = str(anchor)
        if key in out:
            raise ValueError(f"{name} contains duplicate anchor after string normalization: {key!r}")
        score = float(value)
        if not math.isfinite(score):
            raise ValueError(f"{name} score for {key!r} is not finite")
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"{name} score for {key!r} is outside [0, 1]")
        out[key] = score
    return out


def _require_same_anchors(baseline: Mapping[str, float], candidate: Mapping[str, float]) -> list[str]:
    left = set(baseline)
    right = set(candidate)
    if left != right:
        missing_candidate = sorted(left - right)[:5]
        missing_baseline = sorted(right - left)[:5]
        raise ValueError(
            "anchor universe mismatch: "
            f"baseline_only={len(left-right)} sample={missing_candidate}; "
            f"candidate_only={len(right-left)} sample={missing_baseline}"
        )
    return sorted(left)


def _bootstrap_means(
    deltas: np.ndarray,
    *,
    replicates: int,
    seed: int,
    max_draws_per_chunk: int = 2_000_000,
) -> np.ndarray:
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    if max_draws_per_chunk <= 0:
        raise ValueError("max_draws_per_chunk must be positive")
    n = int(deltas.size)
    if n == 0:
        raise ValueError("cannot bootstrap zero entities")
    rng = np.random.default_rng(seed)
    result = np.empty(replicates, dtype=np.float64)
    chunk = max(1, min(256, max_draws_per_chunk // n))
    pos = 0
    while pos < replicates:
        take = min(chunk, replicates - pos)
        idx = rng.integers(0, n, size=(take, n), endpoint=False)
        result[pos : pos + take] = deltas[idx].mean(axis=1)
        pos += take
    return result


def paired_entity_bootstrap(
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
    *,
    replicates: int = 5000,
    seed: int = 517,
    confidence: float = 0.95,
) -> dict[str, float | int | list[float]]:
    """Compare two systems on the exact same entity universe.

    Resampling is paired: each bootstrap draw samples entity indices once and
    applies that draw to the per-entity candidate-minus-baseline differences.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")
    base = _validate_scores("baseline", baseline)
    cand = _validate_scores("candidate", candidate)
    anchors = _require_same_anchors(base, cand)
    deltas = np.asarray([cand[a] - base[a] for a in anchors], dtype=np.float64)
    boot = _bootstrap_means(deltas, replicates=replicates, seed=seed)
    tail = (1.0 - confidence) / 2.0
    lo, hi = np.quantile(boot, [tail, 1.0 - tail])
    return {
        "entities": len(anchors),
        "baseline_mean": float(np.mean([base[a] for a in anchors])),
        "candidate_mean": float(np.mean([cand[a] for a in anchors])),
        "observed_delta": float(deltas.mean()),
        "bootstrap_standard_error": float(boot.std(ddof=1)) if replicates > 1 else 0.0,
        "confidence": float(confidence),
        "percentile_interval": [float(lo), float(hi)],
        "bootstrap_probability_delta_gt_zero": float(np.mean(boot > 0.0)),
        "replicates": int(replicates),
        "seed": int(seed),
    }


def read_score_table(
    path: Path,
    *,
    anchor_col: str = "anchor",
    score_col: str = "row_score",
    slice_col: str | None = None,
) -> tuple[dict[str, float], dict[str, str] | None]:
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
    scores: dict[str, float] = {}
    slices: dict[str, str] | None = {} if slice_col else None
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        required = {anchor_col, score_col} | ({slice_col} if slice_col else set())
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        for line_no, row in enumerate(reader, start=2):
            anchor = (row.get(anchor_col) or "").strip()
            if not anchor:
                raise ValueError(f"{path}:{line_no}: empty anchor")
            if anchor in scores:
                raise ValueError(f"{path}:{line_no}: duplicate anchor {anchor!r}")
            try:
                value = float(row[score_col])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path}:{line_no}: invalid score") from exc
            scores[anchor] = value
            if slices is not None:
                slices[anchor] = str(row[slice_col])
    _validate_scores(str(path), scores)
    return scores, slices


def compare_tables(
    baseline_path: Path,
    candidate_path: Path,
    *,
    anchor_col: str = "anchor",
    score_col: str = "row_score",
    slice_col: str | None = None,
    replicates: int = 5000,
    seed: int = 517,
    confidence: float = 0.95,
) -> dict[str, object]:
    baseline, baseline_slices = read_score_table(
        baseline_path, anchor_col=anchor_col, score_col=score_col, slice_col=slice_col
    )
    candidate, candidate_slices = read_score_table(
        candidate_path, anchor_col=anchor_col, score_col=score_col, slice_col=slice_col
    )
    anchors = _require_same_anchors(baseline, candidate)
    result: dict[str, object] = {
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "all": paired_entity_bootstrap(
            baseline, candidate, replicates=replicates, seed=seed, confidence=confidence
        ),
    }
    if slice_col:
        assert baseline_slices is not None and candidate_slices is not None
        disagree = [a for a in anchors if baseline_slices[a] != candidate_slices[a]]
        if disagree:
            raise ValueError(
                f"slice mismatch for {len(disagree)} anchors; sample={disagree[:5]}"
            )
        slices: dict[str, object] = {}
        for value in sorted(set(baseline_slices.values())):
            members = [a for a in anchors if baseline_slices[a] == value]
            slices[value] = paired_entity_bootstrap(
                {a: baseline[a] for a in members},
                {a: candidate[a] for a in members},
                replicates=replicates,
                seed=seed,
                confidence=confidence,
            )
        result["slice_column"] = slice_col
        result["slices"] = slices
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Paired entity bootstrap for per-anchor row scores")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--anchor-col", default="anchor")
    parser.add_argument("--score-col", default="row_score")
    parser.add_argument("--slice-col")
    parser.add_argument("--replicates", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=517)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_tables(
        args.baseline,
        args.candidate,
        anchor_col=args.anchor_col,
        score_col=args.score_col,
        slice_col=args.slice_col,
        replicates=args.replicates,
        seed=args.seed,
        confidence=args.confidence,
    )
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
