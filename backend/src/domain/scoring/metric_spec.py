"""Declarative metric-spec table: evidence criterion -> Metric (doc 3.3/3.4, design D1/D2).

Each ``MetricSpec`` maps one evidence criterion to one ``Metric`` via ``transform``
(unit conversion) then ``normalize`` (clamped 0-100). Varying normaliser signatures
(``latency``, ``occurrences``) are bound with ``functools.partial`` so every
``normalize`` is ``float -> float``. Pure, deterministic: no clock, no randomness.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from src.domain.enums import Dimension
from src.domain.scoring import normalisation


def identity(value: float) -> float:
    """Pass a raw value through unchanged."""
    return value


def to_percent(value: float) -> float:
    """Rescale a 0-1 ratio to a 0-100 percentage."""
    return value * 100.0


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """Declarative definition of one catalogue metric (design D1)."""

    code: str
    dimension: Dimension
    criterion: str
    unit: str
    weight: float
    transform: Callable[[float], float]
    normalize: Callable[[float], float]


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        code="M-C01",
        dimension=Dimension.CONVERSATIONAL,
        criterion="turn_completion_rate",
        unit="%",
        weight=2.0,
        transform=to_percent,
        normalize=normalisation.percentage_direct,
    ),
    MetricSpec(
        code="M-C02",
        dimension=Dimension.CONVERSATIONAL,
        criterion="prolonged_silence_rate",
        unit="%",
        weight=1.0,
        transform=to_percent,
        normalize=normalisation.percentage_inverse,
    ),
    MetricSpec(
        code="M-C03",
        dimension=Dimension.CONVERSATIONAL,
        criterion="goal_completion",
        unit="bool",
        weight=4.0,
        transform=identity,
        normalize=normalisation.binary,
    ),
    MetricSpec(
        code="M-T01",
        dimension=Dimension.TECHNICAL,
        criterion="mean_turn_latency_seconds",
        unit="seconds",
        weight=3.0,
        transform=identity,
        normalize=partial(normalisation.latency, optimal=1.5, degraded=3.0),
    ),
    MetricSpec(
        code="M-T02",
        dimension=Dimension.TECHNICAL,
        criterion="max_turn_latency_seconds",
        unit="seconds",
        weight=2.0,
        transform=identity,
        normalize=partial(normalisation.latency, optimal=3.0, degraded=5.0),
    ),
    MetricSpec(
        code="M-T03",
        dimension=Dimension.TECHNICAL,
        criterion="technical_error_rate",
        unit="%",
        weight=3.0,
        transform=to_percent,
        normalize=normalisation.percentage_inverse,
    ),
    MetricSpec(
        code="M-T04",
        dimension=Dimension.TECHNICAL,
        criterion="model_invocation_count",
        unit="count",
        weight=0.0,
        transform=identity,
        normalize=normalisation.informational,
    ),
    MetricSpec(
        code="M-O04",
        dimension=Dimension.OPERATIONAL,
        criterion="tool_usage_density",
        unit="ratio",
        weight=0.0,
        transform=to_percent,
        normalize=normalisation.informational,
    ),
    MetricSpec(
        code="M-R01",
        dimension=Dimension.RISK,
        criterion="governance_flag_count",
        unit="count",
        weight=3.0,
        transform=identity,
        normalize=partial(normalisation.occurrences, penalty=33.0),
    ),
    MetricSpec(
        code="M-R02",
        dimension=Dimension.RISK,
        criterion="unrecovered_error_present",
        unit="bool",
        weight=3.0,
        transform=identity,
        normalize=normalisation.binary,
    ),
    MetricSpec(
        code="M-R04",
        dimension=Dimension.RISK,
        criterion="system_warning_rate",
        unit="%",
        weight=1.0,
        transform=to_percent,
        normalize=normalisation.percentage_inverse,
    ),
)
