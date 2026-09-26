#!/usr/bin/env python3
"""Synthetic CatBoost stress test for anchor-balanced early-stopping evaluation."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier, Pool


def anchor_balanced_row_weights(group_ids: np.ndarray) -> np.ndarray:
    groups = np.asarray(group_ids)
    if groups.ndim != 1 or groups.size == 0:
        raise ValueError("group_ids must be a nonempty vector")
    _, inverse, counts = np.unique(groups, return_inverse=True, return_counts=True)
    weights = 1.0 / counts[inverse].astype(np.float64)
    weights /= weights.mean()
    return weights


def make_problem(seed: int = 517):
    rng = np.random.default_rng(seed)
    train_x = rng.normal(size=(3000, 5)).astype(np.float32)
    train_y = (
        2.2 * train_x[:, 0]
        + 0.8 * train_x[:, 1]
        - 0.4 * train_x[:, 2]
        + rng.normal(scale=0.7, size=len(train_x))
        > 0
    ).astype(np.int32)

    ordinary = []
    for anchor in range(19):
        x = rng.normal(size=(10, 5)).astype(np.float32)
        y = (
            2.2 * x[:, 0]
            + 0.8 * x[:, 1]
            - 0.4 * x[:, 2]
            + rng.normal(scale=0.7, size=len(x))
            > 0
        ).astype(np.int32)
        ordinary.append((anchor, x, y))

    hard_x = np.array([[3.0, 1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    hard_y = np.array([0], dtype=np.int32)
    return train_x, train_y, ordinary, hard_x, hard_y


def validation_set(duplicate_hard_rows: int, weighted: bool, seed: int = 517):
    if duplicate_hard_rows < 1:
        raise ValueError("duplicate_hard_rows must be positive")
    _, _, ordinary, hard_x, hard_y = make_problem(seed)
    xs, ys, group_ids = [], [], []
    for anchor, x, y in ordinary:
        xs.append(x)
        ys.append(y)
        group_ids.extend([anchor] * len(x))
    xs.append(np.repeat(hard_x, duplicate_hard_rows, axis=0))
    ys.append(np.repeat(hard_y, duplicate_hard_rows))
    group_ids.extend([19] * duplicate_hard_rows)
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    groups = np.asarray(group_ids, dtype=np.int32)
    if not weighted:
        return (x, y), groups
    return Pool(x, y, weight=anchor_balanced_row_weights(groups)), groups


def train_once(duplicate_hard_rows: int, weighted_eval: bool, seed: int = 517) -> dict:
    train_x, train_y, _, _, _ = make_problem(seed)
    evaluation, groups = validation_set(duplicate_hard_rows, weighted_eval, seed)
    model = CatBoostClassifier(
        iterations=250,
        depth=5,
        learning_rate=0.06,
        loss_function="Logloss",
        eval_metric="Logloss",
        random_seed=seed,
        thread_count=4,
        verbose=False,
        allow_writing_files=False,
        use_best_model=True,
        l2_leaf_reg=5,
    )
    model.fit(train_x, train_y, eval_set=evaluation)
    curve = np.asarray(model.get_evals_result()["validation"]["Logloss"], dtype=float)
    counts = np.bincount(groups)
    return {
        "duplicate_hard_rows": duplicate_hard_rows,
        "weighted_eval": weighted_eval,
        "validation_rows": int(len(groups)),
        "min_anchor_rows": int(counts[counts > 0].min()),
        "max_anchor_rows": int(counts.max()),
        "best_iteration": int(model.get_best_iteration()),
        "tree_count": int(model.tree_count_),
        "best_logloss": float(curve.min()),
        "final_logloss": float(curve[-1]),
    }


def run() -> dict:
    started = time.time()
    cases = [
        train_once(1, False),
        train_once(190, False),
        train_once(1, True),
        train_once(190, True),
    ]
    return {
        "catboost_version": __import__("catboost").__version__,
        "seed": 517,
        "cases": cases,
        "unweighted_best_iteration_shift": cases[1]["best_iteration"] - cases[0]["best_iteration"],
        "weighted_best_iteration_shift": cases[3]["best_iteration"] - cases[2]["best_iteration"],
        "elapsed_seconds": time.time() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = run()
    rendered = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
