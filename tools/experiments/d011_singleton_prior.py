"""D011: test whether source-one observables predict true singleton anchors.

This is a bounded feasibility experiment for the later score-aware singleton gate.
It intentionally does not consume S2/S3 records or claim end-to-end F0.5 gains.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier


SAMPLE_SALT = "sample517:"
FOLD_SALT = "fold517:"


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[^\w]+", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


def fold517(entity_id: str) -> str:
    bucket = int(hashlib.sha256((FOLD_SALT + entity_id).encode()).hexdigest()[:8], 16) % 100
    if bucket < 60:
        return "fit"
    if bucket < 75:
        return "early"
    if bucket < 90:
        return "calibrate"
    return "holdout"


def md5_order(entity_id: str) -> int:
    return int.from_bytes(hashlib.md5((SAMPLE_SALT + entity_id).encode()).digest(), "big")


def select_hash_ordered_source1(path: Path, n: int = 35000):
    """Return the n source-one rows with smallest repo-compatible md5 sample keys."""
    heap = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        required = {"entity_id", "business_name", "business_address", "country"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"source1 missing columns: {sorted(required - set(reader.fieldnames or []))}")
        for row in reader:
            eid = row["entity_id"]
            h = md5_order(eid)
            item = (-h, eid, row["country"], row["business_name"], row["business_address"])
            if len(heap) < n:
                heapq.heappush(heap, item)
            elif h < -heap[0][0]:
                heapq.heapreplace(heap, item)
    return [
        {"entity_id": eid, "country": country, "business_name": name, "business_address": addr}
        for neg_h, eid, country, name, addr in sorted(heap, key=lambda x: -x[0])
    ]


def load_singleton_ids(path: Path) -> set[str]:
    singletons = set()
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        required = {"source1_entity_id", "matched_entity_ids"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"truth missing columns: {sorted(required - set(reader.fieldnames or []))}")
        for row in reader:
            if not row["matched_entity_ids"].strip():
                singletons.add(row["source1_entity_id"])
    return singletons


def add_global_frequency_features(source1_path: Path, selected: list[dict]):
    names = {norm_text(r["business_name"]) for r in selected}
    addrs = {norm_text(r["business_address"]) for r in selected}
    name_counts = Counter()
    addr_counts = Counter()
    with source1_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            n = norm_text(row["business_name"])
            a = norm_text(row["business_address"])
            if n in names:
                name_counts[n] += 1
            if a in addrs:
                addr_counts[a] += 1
    for r in selected:
        r["name_freq"] = name_counts[norm_text(r["business_name"])]
        r["addr_freq"] = addr_counts[norm_text(r["business_address"])]


def text_stats(s: str):
    s = s or ""
    toks = s.split()
    n = len(s)
    digits = sum(ch.isdigit() for ch in s)
    ascii_count = sum(ord(ch) < 128 for ch in s)
    punct = sum((not ch.isalnum()) and (not ch.isspace()) for ch in s)
    return {
        "len": n,
        "tokens": len(toks),
        "digits": digits,
        "digit_frac": digits / max(1, n),
        "nonascii_frac": 1.0 - ascii_count / max(1, n),
        "punct": punct,
        "empty": float(not s.strip()),
    }


FEATURE_NAMES = [
    "country_india",
    "name_len", "name_tokens", "name_digits", "name_digit_frac", "name_nonascii_frac", "name_punct", "name_empty",
    "addr_len", "addr_tokens", "addr_digits", "addr_digit_frac", "addr_nonascii_frac", "addr_punct", "addr_empty",
    "log1p_name_freq", "log1p_addr_freq",
]


def row_features(r: dict):
    ns = text_stats(r["business_name"])
    ad = text_stats(r["business_address"])
    return [
        float(r["country"].strip().lower() == "india"),
        ns["len"], ns["tokens"], ns["digits"], ns["digit_frac"], ns["nonascii_frac"], ns["punct"], ns["empty"],
        ad["len"], ad["tokens"], ad["digits"], ad["digit_frac"], ad["nonascii_frac"], ad["punct"], ad["empty"],
        math.log1p(r["name_freq"]), math.log1p(r["addr_freq"]),
    ]


def rank_metrics(y: np.ndarray, p: np.ndarray):
    y = np.asarray(y, dtype=np.int8)
    p = np.asarray(p, dtype=float)
    if y.size == 0:
        return {}
    eps = 1e-12
    pc = np.clip(p, eps, 1 - eps)
    brier = float(np.mean((p - y) ** 2))
    logloss = float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))
    pos = int(y.sum())
    neg = int(len(y) - pos)
    order = np.argsort(-p, kind="mergesort")
    ys = y[order]
    ps = p[order]
    tp = np.cumsum(ys)
    fp = np.cumsum(1 - ys)
    recall = tp / max(1, pos)
    precision = tp / np.maximum(1, tp + fp)
    avg_precision = float(np.sum(precision[ys == 1]) / max(1, pos))
    if pos and neg:
        distinct = np.r_[np.where(np.diff(ps) != 0)[0], len(ps) - 1]
        tpr = tp[distinct] / pos
        fpr = fp[distinct] / neg
        tpr = np.r_[0.0, tpr, 1.0]
        fpr = np.r_[0.0, fpr, 1.0]
        roc_auc = float(np.trapz(tpr, fpr))
    else:
        roc_auc = None
    return {
        "entities": int(len(y)),
        "singleton_rate": float(y.mean()),
        "roc_auc": roc_auc,
        "average_precision": avg_precision,
        "brier": brier,
        "log_loss": logloss,
    }


def threshold_metrics(y, p, threshold):
    y = np.asarray(y, dtype=np.int8)
    chosen = np.asarray(p) >= threshold
    tp = int(np.sum(chosen & (y == 1)))
    fp = int(np.sum(chosen & (y == 0)))
    fn = int(np.sum((~chosen) & (y == 1)))
    return {
        "threshold": float(threshold),
        "predicted_singleton_rate": float(chosen.mean()),
        "precision": tp / max(1, tp + fp),
        "recall": tp / max(1, tp + fn),
        "tp": tp, "fp": fp, "fn": fn,
    }


def choose_precision_threshold(y, p, min_precision: float):
    candidates = np.unique(np.asarray(p))
    best = None
    for t in candidates:
        m = threshold_metrics(y, p, float(t))
        if m["precision"] >= min_precision and m["tp"] > 0:
            key = (m["recall"], m["precision"], t)
            if best is None or key > best[0]:
                best = (key, m)
    return None if best is None else best[1]["threshold"]


def run(source1: Path, truth: Path):
    start = time.time()
    selected = select_hash_ordered_source1(source1, 35000)
    dev = selected[:30000]
    confirmation_ids = {r["entity_id"] for r in selected[30000:35000]}
    add_global_frequency_features(source1, dev)
    singleton_ids = load_singleton_ids(truth)

    x = np.asarray([row_features(r) for r in dev], dtype=np.float32)
    y = np.asarray([r["entity_id"] in singleton_ids for r in dev], dtype=np.int8)
    folds = np.asarray([fold517(r["entity_id"]) for r in dev])
    countries = np.asarray([r["country"] for r in dev])

    fit = folds == "fit"
    early = folds == "early"
    calibrate = folds == "calibrate"
    holdout = folds == "holdout"

    model = CatBoostClassifier(
        iterations=350,
        depth=5,
        learning_rate=0.04,
        loss_function="Logloss",
        random_seed=517,
        thread_count=4,
        verbose=False,
        allow_writing_files=False,
        l2_leaf_reg=8,
    )
    model.fit(x[fit], y[fit], eval_set=(x[early], y[early]), early_stopping_rounds=40)
    prob = model.predict_proba(x)[:, 1]

    fit_prior = float(y[fit].mean())
    country_prior = {}
    for co in sorted(set(countries[fit])):
        mask = fit & (countries == co)
        country_prior[co] = float(y[mask].mean())
    base_global = np.full(len(y), fit_prior)
    base_country = np.asarray([country_prior.get(co, fit_prior) for co in countries], dtype=float)

    result = {
        "experiment_id": "D011",
        "protocol": {
            "source1_scan": "complete train_source1.tsv, two passes",
            "truth_scan": "complete train_ground_truth.tsv",
            "dev_sample": "first 30,000 anchors by md5('sample517:' + entity_id)",
            "confirmation_guard": "next 5,000 ids identified only to verify disjointness; no confirmation metric is computed",
            "folds": "sha256('fold517:' + entity_id): 60% fit / 15% early / 15% calibrate / 10% holdout",
            "model": "CatBoost depth=5, iterations<=350, lr=0.04, seed=517; fixed before seeing results",
            "features": FEATURE_NAMES,
        },
        "counts": {
            "dev": int(len(dev)),
            "fit": int(fit.sum()), "early": int(early.sum()),
            "calibrate": int(calibrate.sum()), "holdout": int(holdout.sum()),
            "confirmation_ids_guarded": len(confirmation_ids),
            "dev_confirmation_overlap": len({r["entity_id"] for r in dev} & confirmation_ids),
        },
        "fit_singleton_rate": fit_prior,
        "country_fit_singleton_rates": country_prior,
        "holdout": {
            "global_prior": rank_metrics(y[holdout], base_global[holdout]),
            "country_prior": rank_metrics(y[holdout], base_country[holdout]),
            "model": rank_metrics(y[holdout], prob[holdout]),
            "by_country": {},
        },
        "calibration_selected_thresholds": {},
        "holdout_threshold_results": {},
        "feature_importance": dict(sorted(zip(FEATURE_NAMES, map(float, model.feature_importances_)), key=lambda kv: -kv[1])),
        "trees": int(model.tree_count_),
    }

    for co in sorted(set(countries[holdout])):
        m = holdout & (countries == co)
        result["holdout"]["by_country"][co] = rank_metrics(y[m], prob[m])

    for target_precision in (0.80, 0.90, 0.95):
        t = choose_precision_threshold(y[calibrate], prob[calibrate], target_precision)
        key = f"precision_at_least_{target_precision:.2f}"
        result["calibration_selected_thresholds"][key] = t
        result["holdout_threshold_results"][key] = None if t is None else threshold_metrics(y[holdout], prob[holdout], t)

    result["elapsed_seconds"] = time.time() - start
    return result


def self_test():
    assert norm_text("Café, Inc.") == "cafe inc"
    assert fold517("S1-abc") in {"fit", "early", "calibrate", "holdout"}
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.2, 0.8, 0.9])
    m = rank_metrics(y, p)
    assert abs(m["roc_auc"] - 1.0) < 1e-9
    assert abs(m["average_precision"] - 1.0) < 1e-9
    tm = threshold_metrics(y, p, 0.5)
    assert tm["precision"] == 1.0 and tm["recall"] == 1.0
    print("SELF_TEST_PASS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source1", type=Path)
    ap.add_argument("--truth", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.source1 or not args.truth:
        ap.error("--source1 and --truth are required")
    result = run(args.source1, args.truth)
    payload = json.dumps(result, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print("RESULT_JSON=" + payload)


if __name__ == "__main__":
    main()
