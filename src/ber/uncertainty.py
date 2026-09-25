"""Paired entity-level uncertainty utilities for official per-anchor scores."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np


def _as_score_mapping(scores):
    if isinstance(scores, dict):
        items = scores.items()
    else:
        items = scores
    out = {}
    for anchor, score in items:
        anchor = str(anchor)
        if anchor in out:
            raise ValueError(f"duplicate anchor: {anchor}")
        score = float(score)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError(f"score outside [0,1] for {anchor}: {score}")
        out[anchor] = score
    if not out:
        raise ValueError("cannot compare empty score sets")
    return out


def align_scores(baseline, candidate, *, intersection=False):
    baseline = _as_score_mapping(baseline)
    candidate = _as_score_mapping(candidate)
    bkeys, ckeys = set(baseline), set(candidate)
    if bkeys != ckeys and not intersection:
        missing_candidate = sorted(bkeys - ckeys)
        missing_baseline = sorted(ckeys - bkeys)
        raise ValueError(
            "anchor universe mismatch: "
            f"{len(missing_candidate)} missing from candidate, "
            f"{len(missing_baseline)} missing from baseline"
        )
    anchors = sorted(bkeys & ckeys)
    if not anchors:
        raise ValueError("no shared anchors")
    b = np.asarray([baseline[k] for k in anchors], dtype=np.float64)
    c = np.asarray([candidate[k] for k in anchors], dtype=np.float64)
    return anchors, b, c


def exact_sign_test(wins, losses):
    wins, losses = int(wins), int(losses)
    if wins < 0 or losses < 0:
        raise ValueError("wins/losses must be non-negative")
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    numerator = 2 * sum(math.comb(n, i) for i in range(k + 1))
    denominator = 1 << n
    return min(1.0, numerator / denominator)


def paired_bootstrap(baseline, candidate, *, iterations=10000, seed=517,
                     confidence=0.95, intersection=False, chunk_size=256):
    if iterations < 1:
        raise ValueError("iterations must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0,1)")
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    anchors, b, c = align_scores(baseline, candidate, intersection=intersection)
    delta = c - b
    n = len(delta)
    rng = np.random.default_rng(seed)
    boot = np.empty(iterations, dtype=np.float64)
    for start in range(0, iterations, chunk_size):
        end = min(iterations, start + chunk_size)
        indices = rng.integers(0, n, size=(end - start, n))
        boot[start:end] = delta[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    wins = int(np.count_nonzero(delta > 0))
    losses = int(np.count_nonzero(delta < 0))
    ties = n - wins - losses
    return {
        "entities": n,
        "baseline_mean": float(b.mean()),
        "candidate_mean": float(c.mean()),
        "paired_mean_delta": float(delta.mean()),
        "paired_median_delta": float(np.median(delta)),
        "confidence": float(confidence),
        "bootstrap_iterations": int(iterations),
        "bootstrap_seed": int(seed),
        "bootstrap_delta_interval": np.quantile(
            boot, [alpha, 1.0 - alpha]
        ).tolist(),
        "bootstrap_probability_delta_gt_0": float(np.mean(boot > 0)),
        "bootstrap_probability_delta_eq_0": float(np.mean(boot == 0)),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "exact_sign_test_p": exact_sign_test(wins, losses),
    }


def compare_slices(baseline, candidate, metadata, fields, *, iterations=10000,
                   seed=517, confidence=0.95, intersection=False):
    anchors, _, _ = align_scores(
        baseline, candidate, intersection=intersection
    )
    baseline = _as_score_mapping(baseline)
    candidate = _as_score_mapping(candidate)
    missing_meta = [anchor for anchor in anchors if anchor not in metadata]
    if missing_meta:
        raise ValueError(f"metadata missing for {len(missing_meta)} anchors")
    result = {}
    for field_index, field in enumerate(fields):
        values = {}
        for anchor in anchors:
            value = metadata[anchor].get(field)
            if value is None:
                continue
            values.setdefault(str(value), []).append(anchor)
        result[field] = {}
        for value_index, (value, members) in enumerate(sorted(values.items())):
            b = {k: baseline[k] for k in members}
            c = {k: candidate[k] for k in members}
            result[field][value] = paired_bootstrap(
                b, c, iterations=iterations,
                seed=seed + 1009 * (field_index + 1) + value_index,
                confidence=confidence,
            )
    return result


def load_score_tsv(path, anchor_column="anchor", score_column="score",
                   slice_fields=()):
    scores, metadata = {}, {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {anchor_column, score_column, *slice_fields}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} missing columns: {sorted(missing)}")
        for row in reader:
            anchor = row[anchor_column]
            if anchor in scores:
                raise ValueError(f"duplicate anchor in {path}: {anchor}")
            scores[anchor] = float(row[score_column])
            metadata[anchor] = {field: row[field] for field in slice_fields}
    return _as_score_mapping(scores), metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--anchor-column", default="anchor")
    parser.add_argument("--score-column", default="score")
    parser.add_argument("--slice", action="append", default=[])
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=517)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--intersection", action="store_true")
    args = parser.parse_args()

    baseline, baseline_meta = load_score_tsv(
        args.baseline, args.anchor_column, args.score_column, args.slice
    )
    candidate, candidate_meta = load_score_tsv(
        args.candidate, args.anchor_column, args.score_column, args.slice
    )
    for anchor in set(baseline_meta) & set(candidate_meta):
        if baseline_meta[anchor] != candidate_meta[anchor]:
            raise ValueError(f"slice metadata mismatch for anchor {anchor}")

    report = {
        "overall": paired_bootstrap(
            baseline, candidate, iterations=args.iterations, seed=args.seed,
            confidence=args.confidence, intersection=args.intersection,
        ),
        "slices": compare_slices(
            baseline, candidate, baseline_meta, args.slice,
            iterations=args.iterations, seed=args.seed,
            confidence=args.confidence, intersection=args.intersection,
        ) if args.slice else {},
        "intersection_mode": bool(args.intersection),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
