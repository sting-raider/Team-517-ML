"""Full-inventory gate for R031 source-local character frequencies.

Run only with the complete prepared training inventory. This script intentionally
uses the established 4,389 calibration anchors and never touches confirmation
windows.
"""
import argparse
import json
import resource
import sys
import time
from pathlib import Path

from ber.blocking import build_index
from ber.data import connect
from ber.experiment import fold
from ber.retrieval_v3 import (
    build_char_index,
    build_source_char_index,
    evaluate_table,
    fused_candidates,
    source_char_fused_candidates,
)


EXPECTED_PAIR_RECALL = 0.944357161560618
EXPECTED_ORACLE = 0.9804608439335135


def _rss_mb():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def _calibration_meta(c):
    c.execute("""CREATE OR REPLACE TEMP TABLE r031_dev30k AS
        SELECT * FROM train WHERE source=1
        ORDER BY md5('sample517:'||entity_id) LIMIT 30000""")
    selected = [
        (entity_id,)
        for (entity_id,) in c.execute(
            "SELECT entity_id FROM r031_dev30k"
        ).fetchall()
        if fold(entity_id) == "calibrate"
    ]
    if len(selected) != 4389:
        raise ValueError(f"Unexpected calibration universe: {len(selected)}")
    c.execute("CREATE OR REPLACE TEMP TABLE r031_ids(entity_id VARCHAR)")
    c.executemany("INSERT INTO r031_ids VALUES (?)", selected)
    c.execute("""CREATE OR REPLACE TEMP TABLE r031_anchors AS
        SELECT d.* FROM r031_dev30k d JOIN r031_ids USING(entity_id)""")
    return [
        {
            "id": entity_id,
            "country": country,
            "truth": matches.split(",") if matches else [],
        }
        for entity_id, country, matches in c.execute("""SELECT a.entity_id,a.country,t.matches
            FROM r031_anchors a JOIN truth t ON a.entity_id=t.anchor""").fetchall()
    ]


def _true_pair_set(c, table, meta):
    truth = {m["id"]: set(m["truth"]) for m in meta}
    found = set()
    for anchor, target in c.execute(f"""SELECT p.anchor,r.entity_id
        FROM {table} p JOIN train r ON p.rid=r.rowid""").fetchall():
        if target in truth[anchor]:
            found.add((anchor, target))
    return found


def run(db, output):
    started = time.time()
    c = connect(db)
    c.execute("SET memory_limit='20GB'")
    c.execute("SET threads=8")

    build_index(c, "train")
    build_char_index(c, "train")
    meta = _calibration_meta(c)

    phase = time.time()
    fused_candidates(c, "train", "r031_anchors", "r031_baseline", 160)
    baseline = evaluate_table(c, "r031_baseline", meta)
    baseline_seconds = time.time() - phase

    if abs(baseline["candidate_pair_recall"] - EXPECTED_PAIR_RECALL) > 1e-12:
        raise ValueError("INT003 pair-recall baseline reproduction failed")
    if abs(baseline["blocking_oracle_macro_f0_5"] - EXPECTED_ORACLE) > 1e-12:
        raise ValueError("INT003 oracle baseline reproduction failed")

    phase = time.time()
    build_source_char_index(c, "train")
    source_index_seconds = time.time() - phase

    phase = time.time()
    source_char_fused_candidates(
        c, "train", "r031_anchors", "r031_source_char", 160
    )
    changed = evaluate_table(c, "r031_source_char", meta)
    source_query_seconds = time.time() - phase

    baseline_true = _true_pair_set(c, "r031_baseline", meta)
    changed_true = _true_pair_set(c, "r031_source_char", meta)
    recovered = changed_true - baseline_true
    lost = baseline_true - changed_true

    result = {
        "experiment": "R031",
        "protocol": (
            "Complete train S2/S3 inventory; exact 4,389 fold517 calibration anchors; "
            "INT003 lexical+pooled-char RRF160 vs lexical+source-local-char RRF160; "
            "same lexical top160, char top64, six unique query grams per c3/c4 family, "
            "and final cap160."
        ),
        "baseline": baseline,
        "source_local_char": changed,
        "delta": {
            "candidate_pair_recall": (
                changed["candidate_pair_recall"]
                - baseline["candidate_pair_recall"]
            ),
            "candidate_entity_recall": (
                changed["candidate_entity_recall"]
                - baseline["candidate_entity_recall"]
            ),
            "all_matches_retrieved_rate": (
                changed["all_matches_retrieved_rate"]
                - baseline["all_matches_retrieved_rate"]
            ),
            "blocking_oracle_macro_f0_5": (
                changed["blocking_oracle_macro_f0_5"]
                - baseline["blocking_oracle_macro_f0_5"]
            ),
            "mean_candidates": (
                changed["mean_candidates"] - baseline["mean_candidates"]
            ),
        },
        "true_pair_diff": {
            "recovered": len(recovered),
            "lost": len(lost),
            "net": len(recovered) - len(lost),
        },
        "seconds": {
            "baseline_query": baseline_seconds,
            "source_char_index": source_index_seconds,
            "source_char_query": source_query_seconds,
            "total": time.time() - started,
        },
        "max_rss_mb": _rss_mb(),
        "integrity": {
            "expected_pair_recall": EXPECTED_PAIR_RECALL,
            "expected_oracle": EXPECTED_ORACLE,
            "confirmation_consumed": False,
            "candidate_cap": 160,
        },
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    c.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.db, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
