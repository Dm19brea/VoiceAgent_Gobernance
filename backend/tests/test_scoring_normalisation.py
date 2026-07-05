"""M4.2 — Normalisation functions (doc 3.4.2, spec S1)."""

from src.domain.scoring.normalisation import (
    binary,
    latency,
    occurrences,
    percentage_direct,
    percentage_inverse,
)


def test_percentage_direct_returns_value() -> None:
    assert percentage_direct(87) == 87


def test_percentage_inverse_is_hundred_minus_value() -> None:
    assert percentage_inverse(8) == 92


def test_binary_maps_one_to_hundred_and_zero_to_zero() -> None:
    assert binary(1) == 100
    assert binary(0) == 0


def test_occurrences_applies_penalty_per_occurrence() -> None:
    assert occurrences(2, penalty=33) == 34


def test_latency_interpolates_linearly_between_optimal_and_degraded() -> None:
    assert latency(2000, optimal=1500, degraded=3000) == 67


def test_latency_is_full_score_at_or_below_optimal() -> None:
    assert latency(1000, optimal=1500, degraded=3000) == 100


def test_latency_is_zero_at_or_above_degraded() -> None:
    assert latency(3500, optimal=1500, degraded=3000) == 0


def test_percentage_direct_clamps_above_hundred() -> None:
    assert percentage_direct(150) == 100


def test_percentage_inverse_clamps_below_zero() -> None:
    assert percentage_inverse(150) == 0


def test_occurrences_clamps_at_zero() -> None:
    assert occurrences(10, penalty=33) == 0
