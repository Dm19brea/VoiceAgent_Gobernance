from dataclasses import dataclass

from src.domain.enums import Dimension


@dataclass(frozen=True, slots=True)
class Metric:
    """A computed metric: a raw value normalised to a 0-100 score within a dimension (R2)."""

    code: str
    dimension: Dimension
    raw_value: float
    normalized_score: float
    weight: float
    unit: str
