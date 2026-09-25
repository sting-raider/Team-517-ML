"""Opt-in M002 candidate-rank and blocker-provenance matcher features."""
import math


PROVENANCE_FEATURE_NAMES = [
    'candidate_rank',
    'name_exact_hits',
    'address_exact_hits',
    'name_token_hits',
    'address_token_hits',
    'address_bigram_hits',
    'name_number_hits',
    'address_number_hits',
    'log_min_key_freq',
]


def provenance_values(candidate_rank, name_exact_hits, address_exact_hits, name_token_hits,
                      address_token_hits, address_bigram_hits, name_number_hits,
                      address_number_hits, min_key_freq):
    values = [
        candidate_rank, name_exact_hits, address_exact_hits, name_token_hits,
        address_token_hits, address_bigram_hits, name_number_hits,
        address_number_hits, min_key_freq,
    ]
    if candidate_rank < 1:
        raise ValueError('candidate_rank must be >= 1')
    if min_key_freq < 1:
        raise ValueError('min_key_freq must be >= 1')
    if any(v < 0 for v in values[1:-1]):
        raise ValueError('provenance hit counts must be non-negative')
    return [
        float(candidate_rank),
        float(name_exact_hits),
        float(address_exact_hits),
        float(name_token_hits),
        float(address_token_hits),
        float(address_bigram_hits),
        float(name_number_hits),
        float(address_number_hits),
        math.log1p(float(min_key_freq)),
    ]
