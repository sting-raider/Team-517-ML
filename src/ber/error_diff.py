"""Paired anchor-level error diffs for entity-resolution experiments."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from .metrics import row_score


_RESERVED = {
    "anchor", "id", "score", "truth_count", "predicted_count", "candidate_count"
}


def cardinality_bucket(truth_count):
    n = int(truth_count)
    if n == 0:
        return "singleton"
    if n == 1:
        return "one"
    if n <= 3:
        return "two_to_three"
    if n <= 9:
        return "four_to_nine"
    return "ten_plus"


def make_rows(truth, predicted, candidates=None, metadata=None):
    """Build deterministic per-anchor evaluation rows from exact evaluation mappings."""
    metadata = metadata or {}
    rows = []
    for anchor in sorted(truth):
        t = set(truth[anchor])
        p = set(predicted.get(anchor, ()))
        row = {
            "anchor": str(anchor),
            "score": float(row_score(t, p)),
            "truth_count": len(t),
            "predicted_count": len(p),
        }
        if candidates is not None:
            row["candidate_count"] = len(set(candidates.get(anchor, ())))
        extra = dict(metadata.get(anchor, {}))
        overlap = _RESERVED & set(extra)
        if overlap:
            raise ValueError(
                f"Metadata for {anchor} overwrites reserved fields: {sorted(overlap)}"
            )
        row.update(extra)
        rows.append(row)
    return rows


def write_rows(path, rows):
    """Write one compact JSON object per anchor."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in sorted(rows, key=lambda r: str(r["anchor"])):
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _coerce_row(row):
    row = dict(row)
    anchor = row.get("anchor", row.get("id"))
    if anchor is None or str(anchor) == "":
        raise ValueError("Every row needs a non-empty 'anchor' (or 'id')")
    if "score" not in row:
        raise ValueError(f"Row {anchor} is missing 'score'")
    row["anchor"] = str(anchor)
    row["score"] = float(row["score"])
    for key in ("truth_count", "predicted_count", "candidate_count"):
        if key in row and row[key] not in (None, ""):
            row[key] = int(row[key])
        elif key in row:
            row[key] = None
    return row


def load_rows(path):
    """Load JSONL, JSON list/{rows:[...]}, or TSV anchor-score rows."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        with path.open(encoding="utf-8", newline="") as f:
            rows = [_coerce_row(r) for r in csv.DictReader(f, delimiter="\t")]
    elif suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            if "rows" not in payload:
                raise ValueError("JSON object input must contain a 'rows' list")
            payload = payload["rows"]
        if not isinstance(payload, list):
            raise ValueError("JSON input must be a list or an object containing 'rows'")
        rows = [_coerce_row(r) for r in payload]
    else:
        rows = []
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    rows.append(_coerce_row(json.loads(line)))
                except Exception as exc:
                    raise ValueError(f"{path}:{lineno}: {exc}") from exc
    _index(rows)
    return rows


def _index(rows):
    indexed = {}
    for row in rows:
        row = _coerce_row(row)
        anchor = row["anchor"]
        if anchor in indexed:
            raise ValueError(f"Duplicate anchor: {anchor}")
        indexed[anchor] = row
    return indexed


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def _paired_summary(anchors, baseline, challenger, epsilon):
    deltas = [challenger[a]["score"] - baseline[a]["score"] for a in anchors]
    return {
        "entities": len(anchors),
        "baseline_macro_f0_5": _mean(baseline[a]["score"] for a in anchors),
        "challenger_macro_f0_5": _mean(challenger[a]["score"] for a in anchors),
        "delta": _mean(deltas),
        "improved": sum(d > epsilon for d in deltas),
        "regressed": sum(d < -epsilon for d in deltas),
        "unchanged": sum(abs(d) <= epsilon for d in deltas),
    }


def _check_invariants(anchors, baseline, challenger):
    for anchor in anchors:
        b, c = baseline[anchor], challenger[anchor]
        for key in ("country", "source", "truth_count"):
            if key in b and key in c:
                bv, cv = b[key], c[key]
                if bv not in (None, "") and cv not in (None, "") and bv != cv:
                    raise ValueError(
                        f"Invariant metadata mismatch for {anchor}: {key}={bv!r} vs {cv!r}"
                    )


def compare_rows(
    baseline_rows,
    challenger_rows,
    *,
    allow_intersection=False,
    epsilon=1e-12,
    top_n=20,
):
    """Compare two evaluations on the same anchor universe."""
    baseline = _index(baseline_rows)
    challenger = _index(challenger_rows)
    b_ids, c_ids = set(baseline), set(challenger)
    only_baseline = sorted(b_ids - c_ids)
    only_challenger = sorted(c_ids - b_ids)
    exact = b_ids == c_ids
    if not exact and not allow_intersection:
        raise ValueError(
            "Anchor-set mismatch: "
            f"{len(only_baseline)} only in baseline, "
            f"{len(only_challenger)} only in challenger; "
            "use --allow-intersection only for an explicitly non-paired diagnostic"
        )
    anchors = sorted(b_ids & c_ids)
    if not anchors:
        raise ValueError("No shared anchors to compare")
    _check_invariants(anchors, baseline, challenger)

    result = {
        "universe": {
            "exact_anchor_match": exact,
            "compared_entities": len(anchors),
            "baseline_entities": len(baseline),
            "challenger_entities": len(challenger),
            "only_baseline_count": len(only_baseline),
            "only_challenger_count": len(only_challenger),
            "only_baseline_examples": only_baseline[:10],
            "only_challenger_examples": only_challenger[:10],
        },
        "overall": _paired_summary(anchors, baseline, challenger, epsilon),
        "slices": {},
    }

    dimensions = {}
    if any(baseline[a].get("country") not in (None, "") for a in anchors):
        dimensions["country"] = lambda a: baseline[a].get("country")
    if any(baseline[a].get("source") not in (None, "") for a in anchors):
        dimensions["source"] = lambda a: baseline[a].get("source")
    if all(baseline[a].get("truth_count") is not None for a in anchors):
        dimensions["cardinality"] = lambda a: cardinality_bucket(
            baseline[a]["truth_count"]
        )

    for dimension, key_fn in dimensions.items():
        groups = defaultdict(list)
        for anchor in anchors:
            key = key_fn(anchor)
            if key not in (None, ""):
                groups[str(key)].append(anchor)
        result["slices"][dimension] = {
            key: _paired_summary(group, baseline, challenger, epsilon)
            for key, group in sorted(groups.items())
        }

    changes = []
    for anchor in anchors:
        b, c = baseline[anchor], challenger[anchor]
        item = {
            "anchor": anchor,
            "baseline_score": b["score"],
            "challenger_score": c["score"],
            "delta": c["score"] - b["score"],
        }
        for key in ("country", "source", "truth_count"):
            if b.get(key) not in (None, ""):
                item[key] = b[key]
        for key in ("predicted_count", "candidate_count"):
            if b.get(key) is not None:
                item[f"baseline_{key}"] = b[key]
            if c.get(key) is not None:
                item[f"challenger_{key}"] = c[key]
        changes.append(item)
    changes.sort(key=lambda r: (-abs(r["delta"]), r["anchor"]))
    result["largest_changes"] = changes[: max(0, int(top_n))]
    return result


def main():
    p = argparse.ArgumentParser(
        description="Strict paired anchor-level diff for two ER evaluation row files"
    )
    p.add_argument("baseline", type=Path)
    p.add_argument("challenger", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--allow-intersection", action="store_true")
    p.add_argument("--epsilon", type=float, default=1e-12)
    p.add_argument("--top-n", type=int, default=20)
    a = p.parse_args()
    result = compare_rows(
        load_rows(a.baseline),
        load_rows(a.challenger),
        allow_intersection=a.allow_intersection,
        epsilon=a.epsilon,
        top_n=a.top_n,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
