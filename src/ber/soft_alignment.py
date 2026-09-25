"""Deterministic one-to-one soft token alignment for normalized address text."""
from rapidfuzz.distance import JaroWinkler


ADDRESS_SOFT_ALIGNMENT_FEATURE_NAMES = [
    "address_soft_left_coverage",
    "address_soft_right_coverage",
    "address_soft_hmean",
    "address_soft_strong_fraction",
    "address_soft_exact_fraction",
]


def _token_similarity(left, right):
    """Conservative similarity for already-normalized address tokens."""
    if left == right:
        return 1.0
    # Address numbers and short components are too collision-prone for fuzzy credit.
    if left.isdigit() or right.isdigit() or min(len(left), len(right)) < 3:
        return 0.0
    return float(JaroWinkler.normalized_similarity(left, right))


def address_soft_alignment_features(
    left, right, min_similarity=0.60, strong_similarity=0.88
):
    """Return bounded one-to-one address-token alignment features.

    Each token participates in at most one match. Candidate token pairs are
    considered by descending similarity with token positions as deterministic
    tie breakers. Empty input is deliberately not rewarded because the legacy
    matcher already has explicit missing-address features.
    """
    left_tokens = tuple(token for token in left.split() if token)
    right_tokens = tuple(token for token in right.split() if token)
    if not left_tokens or not right_tokens:
        return [0.0] * len(ADDRESS_SOFT_ALIGNMENT_FEATURE_NAMES)

    # Exact pairs always outrank fuzzy pairs, so consume them first. Besides
    # making that precedence explicit, this removes common shared tokens from
    # the O(left * right) fuzzy cross-product.
    right_exact = {}
    for j, token in enumerate(right_tokens):
        right_exact.setdefault(token, []).append(j)
    right_offsets = {token: 0 for token in right_exact}
    used_left = set()
    used_right = set()
    matches = []
    for i, token in enumerate(left_tokens):
        positions = right_exact.get(token)
        offset = right_offsets.get(token, 0)
        if positions is None or offset >= len(positions):
            continue
        j = positions[offset]
        right_offsets[token] = offset + 1
        used_left.add(i)
        used_right.add(j)
        matches.append(1.0)

    pairs = []
    for i, left_token in enumerate(left_tokens):
        if i in used_left:
            continue
        for j, right_token in enumerate(right_tokens):
            if j in used_right:
                continue
            score = _token_similarity(left_token, right_token)
            if score >= min_similarity:
                pairs.append((-score, i, j))
    pairs.sort()

    for negative_score, i, j in pairs:
        if i in used_left or j in used_right:
            continue
        used_left.add(i)
        used_right.add(j)
        matches.append(-negative_score)

    total = float(sum(matches))
    left_coverage = total / len(left_tokens)
    right_coverage = total / len(right_tokens)
    coverage_sum = left_coverage + right_coverage
    harmonic_coverage = (
        2.0 * left_coverage * right_coverage / coverage_sum if coverage_sum else 0.0
    )
    denominator = max(len(left_tokens), len(right_tokens))
    strong_fraction = (
        sum(score >= strong_similarity for score in matches) / denominator
    )
    exact_fraction = sum(score == 1.0 for score in matches) / denominator
    return [
        left_coverage,
        right_coverage,
        harmonic_coverage,
        strong_fraction,
        exact_fraction,
    ]
