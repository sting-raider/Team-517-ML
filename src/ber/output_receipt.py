"""Aggregate per-country output accounting for streaming submission validation.

Pure bookkeeping only: this module does not inspect labels or alter predictions.
"""


def new_country_counts():
    return {}


def add_country_row(counts, country, candidates, predicted):
    """Accumulate one Source-1 row into an open-ended country map."""
    if not isinstance(country, str):
        raise TypeError("country must be a string")
    row = counts.setdefault(country, {
        "anchors": 0,
        "candidates": 0,
        "matches": 0,
        "empty_predictions": 0,
    })
    row["anchors"] += 1
    row["candidates"] += len(candidates)
    row["matches"] += len(predicted)
    row["empty_predictions"] += int(not predicted)


def ordered_country_counts(counts):
    """Return deterministic plain dictionaries suitable for JSON receipts."""
    return {
        country: {
            "anchors": values["anchors"],
            "candidates": values["candidates"],
            "matches": values["matches"],
            "empty_predictions": values["empty_predictions"],
        }
        for country, values in sorted(counts.items())
    }
