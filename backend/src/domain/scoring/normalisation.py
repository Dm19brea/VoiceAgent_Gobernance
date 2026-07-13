"""Pure normalisation functions mapping raw metric values to a 0-100 score (doc 3.4.2).

Each function is deterministic and side-effect free: no state, no clock, no randomness.
Results are always clamped to the closed interval [0, 100].
"""


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def percentage_direct(value: float) -> float:
    """A percentage where higher is better maps straight to the score."""
    return _clamp(value)


def percentage_inverse(value: float) -> float:
    """A percentage where lower is better maps to its complement (100 - value)."""
    return _clamp(100.0 - value)


def binary(value: float) -> float:
    """A boolean-like value: truthy becomes 100, falsy becomes 0."""
    return 100.0 if value else 0.0


def occurrences(count: float, penalty: float) -> float:
    """Each occurrence subtracts ``penalty`` points from a perfect score."""
    return _clamp(100.0 - count * penalty)


def latency(value: float, optimal: float, degraded: float) -> float:
    """Full score at or below ``optimal``, zero at or above ``degraded``, linear between."""
    if value <= optimal:
        return 100.0
    if value >= degraded:
        return 0.0
    ratio = (degraded - value) / (degraded - optimal)
    return _clamp(round(ratio * 100.0))


def informational(value: float) -> float:
    """A metric with no scoring threshold: always neutral, never penalises (weight 0)."""
    del value
    return 100.0
