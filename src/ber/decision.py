"""Exact small-set expected-F0.5 decisions under independent Bernoulli labels.

This module is intentionally a bounded decision kernel, not a production decoder for
hundreds of candidates per anchor. It assumes the supplied candidate probabilities
cover the complete truth set and are mutually independent. Both assumptions must be
validated or explicitly modeled before end-to-end deployment.
"""
from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class ExpectedF05Decision:
    """Best probability-ranked prefix and its exact expected row utility."""

    selected_indices: tuple[int, ...]
    prefix_size: int
    expected_f0_5: float
    sorted_indices: tuple[int, ...]
    prefix_utilities: tuple[float, ...]


def _validated_probabilities(probabilities: Iterable[float], max_candidates: int) -> list[float]:
    if max_candidates < 0:
        raise ValueError("max_candidates must be non-negative")
    values = [float(p) for p in probabilities]
    if len(values) > max_candidates:
        raise ValueError(
            f"Exact expected-F0.5 decoder is bounded to {max_candidates} candidates; "
            f"received {len(values)}. Prefilter explicitly rather than silently truncating."
        )
    for p in values:
        if not math.isfinite(p) or not 0.0 <= p <= 1.0:
            raise ValueError(f"Probability must be finite and in [0, 1], got {p!r}")
    return values


def _extend_count_distribution(distribution: list[float], probability: float) -> list[float]:
    """Poisson-binomial count distribution after adding one Bernoulli variable."""
    out = [0.0] * (len(distribution) + 1)
    miss = 1.0 - probability
    for count, mass in enumerate(distribution):
        out[count] += mass * miss
        out[count + 1] += mass * probability
    return out


def expected_f05_prefix_utilities(
    probabilities: Iterable[float],
    *,
    max_candidates: int = 64,
) -> tuple[tuple[int, ...], tuple[float, ...]]:
    """Return stable probability order and exact expected F0.5 for every prefix.

    Utility index k corresponds to predicting the first k candidates after sorting by
    descending probability (stable original-index tie break). Index zero is the empty
    prediction.

    For k > 0, if T is the number of true candidates inside the predicted prefix and
    F is the number of true candidates outside it, row F0.5 is:

        1.25 * T / (k + 0.25 * (T + F)).

    Prefix and suffix Poisson-binomial distributions make the expectation exact under
    independent Bernoulli candidate labels. For a fixed prediction size, replacing a
    selected lower-probability item with an unselected higher-probability item can only
    increase expected utility: the F0.5 denominator depends on total truth cardinality,
    so the two one-positive swap states share the same denominator and their expected
    difference is proportional to p_high - p_low. Therefore searching probability
    prefixes covers the exact optimum under these assumptions. Empty-set utility is
    exactly P(|truth|=0).

    The complete-truth assumption matters: positives missing from retrieval are not
    represented by these probabilities and therefore are not included in this
    expectation.
    """
    values = _validated_probabilities(probabilities, max_candidates)
    ordered = sorted(enumerate(values), key=lambda item: (-item[1], item[0]))
    order = tuple(index for index, _ in ordered)
    probs = [p for _, p in ordered]
    n = len(probs)

    prefix: list[list[float]] = [[1.0]]
    for p in probs:
        prefix.append(_extend_count_distribution(prefix[-1], p))

    suffix: list[list[float]] = [[] for _ in range(n + 1)]
    suffix[n] = [1.0]
    for index in range(n - 1, -1, -1):
        suffix[index] = _extend_count_distribution(suffix[index + 1], probs[index])

    utilities = [suffix[0][0]]
    for k in range(1, n + 1):
        utility = 0.0
        for true_selected, selected_mass in enumerate(prefix[k]):
            if true_selected == 0 or selected_mass == 0.0:
                continue
            for true_unselected, unselected_mass in enumerate(suffix[k]):
                if unselected_mass == 0.0:
                    continue
                truth_size = true_selected + true_unselected
                score = 1.25 * true_selected / (k + 0.25 * truth_size)
                utility += selected_mass * unselected_mass * score
        utilities.append(utility)

    return order, tuple(utilities)


def choose_expected_f05_prefix(
    probabilities: Iterable[float],
    *,
    max_candidates: int = 64,
    tie_tolerance: float = 1e-12,
) -> ExpectedF05Decision:
    """Choose the exact-utility probability prefix, preferring fewer predictions on ties."""
    if tie_tolerance < 0:
        raise ValueError("tie_tolerance must be non-negative")
    order, utilities = expected_f05_prefix_utilities(
        probabilities, max_candidates=max_candidates
    )
    best = 0
    for k in range(1, len(utilities)):
        if utilities[k] > utilities[best] + tie_tolerance:
            best = k
    return ExpectedF05Decision(
        selected_indices=order[:best],
        prefix_size=best,
        expected_f0_5=utilities[best],
        sorted_indices=order,
        prefix_utilities=utilities,
    )
