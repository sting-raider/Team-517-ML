"""Reference analysis for cross-source posting-frequency pooling in blocker v2.

This module does not change production retrieval. It isolates the frequency cutoff
and IDF-like weighting semantics so cross-source coupling can be tested without
challenge rows.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceFrequency:
    source2: int
    source3: int

    def __post_init__(self) -> None:
        if self.source2 < 0 or self.source3 < 0:
            raise ValueError("frequencies must be non-negative")

    @property
    def pooled(self) -> int:
        return self.source2 + self.source3


def pooled_eligible(freq: SourceFrequency, cutoff: int = 1000) -> bool:
    return 0 < freq.pooled <= cutoff


def source_eligible(freq: SourceFrequency, source: int, cutoff: int = 1000) -> bool:
    value = _source_value(freq, source)
    return 0 < value <= cutoff


def _source_value(freq: SourceFrequency, source: int) -> int:
    if source == 2:
        return freq.source2
    if source == 3:
        return freq.source3
    raise ValueError("source must be 2 or 3")


def retrieval_weight(
    posting_freq: int,
    corpus_constant: float = 10_000_001.0,
) -> float:
    if posting_freq <= 0:
        raise ValueError("posting_freq must be positive")
    return math.log(corpus_constant / posting_freq)


def pooled_weight(freq: SourceFrequency) -> float:
    if freq.pooled <= 0:
        raise ValueError("pooled frequency must be positive")
    return retrieval_weight(freq.pooled)


def source_weight(freq: SourceFrequency, source: int) -> float:
    value = _source_value(freq, source)
    return retrieval_weight(value)


def audit_case(freq: SourceFrequency, cutoff: int = 1000) -> dict[str, object]:
    result: dict[str, object] = {
        "source2_freq": freq.source2,
        "source3_freq": freq.source3,
        "pooled_freq": freq.pooled,
        "pooled_eligible": pooled_eligible(freq, cutoff),
    }
    for source in (2, 3):
        value = _source_value(freq, source)
        result[f"source{source}_eligible"] = source_eligible(
            freq, source, cutoff
        )
        if value > 0:
            result[f"source{source}_pooled_weight"] = pooled_weight(freq)
            result[f"source{source}_specific_weight"] = source_weight(
                freq, source
            )
            result[f"source{source}_weight_loss"] = (
                source_weight(freq, source) - pooled_weight(freq)
            )
    return result


def demo() -> dict[str, dict[str, object]]:
    cases = {
        "rare_s3_suppressed_by_common_s2": SourceFrequency(1001, 1),
        "both_below_cutoff_but_pooled_above": SourceFrequency(600, 600),
        "rare_s2_weight_diluted_by_common_s3": SourceFrequency(1, 999),
        "pooled_and_source_specific_agree": SourceFrequency(400, 300),
        "both_sources_individually_too_common": SourceFrequency(1200, 1500),
    }
    return {name: audit_case(freq) for name, freq in cases.items()}


if __name__ == "__main__":
    import json

    print(json.dumps(demo(), indent=2, sort_keys=True))
