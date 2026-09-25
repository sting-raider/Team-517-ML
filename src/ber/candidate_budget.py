"""Measure the final-model quality and blocking cost at smaller candidate budgets."""
import json
from pathlib import Path
import numpy as np

from .candidate_budget_contract import raw_retrieval_rank
from .experiment import choose_threshold, mappings
from .metrics import evaluate


def main():
    root = Path("artifacts/wide_calibration")
    data = np.load(root / "features.npz")
    x = data["x"]
    groups = data["groups"]
    target = data["target"]
    meta = json.loads((root / "anchors.json").read_text(encoding="utf-8"))
    prob = np.load("artifacts/tuned/depth10_wide_probabilities.npy")
    if len(prob) != len(groups):
        raise ValueError("Feature and prediction arrays have different lengths")
    rank = raw_retrieval_rank(groups, target, x[:, -3])
    del x, data
    report = {"protocol": "Same 4,389 calibration anchors and depth-10 model at each raw retrieval cap",
              "selection_note": "Organizer review explicitly rewards smaller candidate sets; these calibration results are not independent confirmation",
              "caps": {}}
    for cap in (20, 30, 40, 50, 80, 120, 160, 240, 320, 640):
        keep = rank <= cap
        threshold, _ = choose_threshold(meta, groups[keep], target[keep], prob[keep], range(len(meta)))
        truth, predicted, candidate = mappings(meta, groups[keep], target[keep], prob[keep], range(len(meta)), threshold)
        metrics = evaluate(truth, predicted, candidate)
        report["caps"][str(cap)] = {"threshold": threshold,
                                     "mean_candidates": int(keep.sum()) / len(meta), **metrics}
        print(cap, round(metrics["macro_f0_5"], 6), round(int(keep.sum()) / len(meta), 1), flush=True)
    Path("reports/candidate_budget.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
