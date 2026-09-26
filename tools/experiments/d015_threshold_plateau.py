"""Audit a threshold/F0.5 calibration curve for near-optimal plateau structure."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def analyze_curve(curve: list[dict], epsilons=(0.0005, 0.001, 0.002, 0.005)) -> dict:
    if not curve:
        raise ValueError("curve must be non-empty")
    points = [(float(p["threshold"]), float(p["macro_f0_5"])) for p in curve]
    if any(not math.isfinite(t) or not math.isfinite(s) for t, s in points):
        raise ValueError("curve contains non-finite values")
    thresholds = [t for t, _ in points]
    if thresholds != sorted(thresholds) or len(set(thresholds)) != len(thresholds):
        raise ValueError("thresholds must be strictly increasing and unique")
    best_i = max(range(len(points)), key=lambda i: (points[i][1], points[i][0]))
    best_t, best_s = points[best_i]

    neighbors = {}
    if best_i > 0:
        t, s = points[best_i - 1]
        neighbors["left"] = {"threshold": t, "macro_f0_5": s, "loss": best_s - s}
    if best_i + 1 < len(points):
        t, s = points[best_i + 1]
        neighbors["right"] = {"threshold": t, "macro_f0_5": s, "loss": best_s - s}

    bands = {}
    for epsilon in epsilons:
        epsilon = float(epsilon)
        if epsilon < 0:
            raise ValueError("epsilon must be non-negative")
        good = [s >= best_s - epsilon for _, s in points]
        lo = hi = best_i
        while lo > 0 and good[lo - 1]:
            lo -= 1
        while hi + 1 < len(points) and good[hi + 1]:
            hi += 1
        low_t, high_t = points[lo][0], points[hi][0]
        midpoint = (low_t + high_t) / 2
        bands[f"{epsilon:g}"] = {
            "low_threshold": low_t,
            "high_threshold": high_t,
            "width": high_t - low_t,
            "midpoint": midpoint,
            "best_offset_from_midpoint": best_t - midpoint,
            "grid_points": hi - lo + 1,
            "worst_score_in_component": min(s for _, s in points[lo : hi + 1]),
        }

    return {
        "best_threshold": best_t,
        "best_macro_f0_5": best_s,
        "neighbors": neighbors,
        "epsilon_optimal_components": bands,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--artifact", type=Path, required=True)
    p.add_argument("--eps", nargs="*", type=float, default=[0.0005, 0.001, 0.002, 0.005])
    args = p.parse_args()
    payload = json.loads(args.artifact.read_text(encoding="utf-8"))
    result = analyze_curve(payload["calibration_curve"], args.eps)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
