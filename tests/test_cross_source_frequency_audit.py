import math
import random

import pytest

from ber.cross_source_frequency_audit import (
    SourceFrequency,
    audit_case,
    pooled_eligible,
    pooled_weight,
    retrieval_weight,
    source_eligible,
    source_weight,
)


def test_rare_source3_key_can_be_dropped_by_common_source2():
    freq = SourceFrequency(1001, 1)
    assert not pooled_eligible(freq)
    assert not source_eligible(freq, 2)
    assert source_eligible(freq, 3)


def test_two_individually_eligible_sources_can_cross_pooled_cutoff():
    freq = SourceFrequency(600, 600)
    assert not pooled_eligible(freq)
    assert source_eligible(freq, 2)
    assert source_eligible(freq, 3)


def test_cross_source_pooling_dilutes_rare_source_weight_by_log_ratio():
    freq = SourceFrequency(1, 999)
    loss = source_weight(freq, 2) - pooled_weight(freq)
    assert math.isclose(loss, math.log(1000.0), rel_tol=1e-12)
    assert loss > 6.9


def test_no_weight_loss_when_other_source_has_zero_postings():
    freq = SourceFrequency(7, 0)
    assert math.isclose(
        source_weight(freq, 2),
        pooled_weight(freq),
        rel_tol=0,
        abs_tol=0,
    )


def test_source_specific_eligibility_is_superset_of_pooled_eligibility():
    rng = random.Random(517020)
    for _ in range(10_000):
        freq = SourceFrequency(
            rng.randrange(0, 2000),
            rng.randrange(0, 2000),
        )
        if pooled_eligible(freq):
            if freq.source2 > 0:
                assert source_eligible(freq, 2)
            if freq.source3 > 0:
                assert source_eligible(freq, 3)


def test_source_specific_accounting_never_decreases_rare_source_weight():
    rng = random.Random(517021)
    for _ in range(10_000):
        freq = SourceFrequency(
            rng.randrange(1, 3000),
            rng.randrange(1, 3000),
        )
        assert source_weight(freq, 2) >= pooled_weight(freq)
        assert source_weight(freq, 3) >= pooled_weight(freq)


def test_audit_case_reports_expected_cutoff_and_weight_loss():
    result = audit_case(SourceFrequency(1, 999))
    assert result["pooled_freq"] == 1000
    assert result["pooled_eligible"] is True
    assert result["source2_eligible"] is True
    assert result["source3_eligible"] is True
    assert result["source2_weight_loss"] > 6.9


def test_invalid_source_and_frequency_are_rejected():
    with pytest.raises(ValueError):
        SourceFrequency(-1, 0)
    with pytest.raises(ValueError):
        source_eligible(SourceFrequency(1, 1), 4)
    with pytest.raises(ValueError):
        retrieval_weight(0)
