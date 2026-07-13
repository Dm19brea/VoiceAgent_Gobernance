"""M4 metric catalogue: compute metrics from a session's evidences (doc 3.3, design D1/D2).

Pure and deterministic. Metrics whose source evidence is absent are omitted, never
faked (R10). Most metrics are built generically from ``METRIC_SPECS``; ``engagement``
(dual-evidence) and ``duration`` stay special-cased inline as irregular legacy signals.
"""

from collections.abc import Sequence

from src.domain.enums import Dimension
from src.domain.evidence import Evidence
from src.domain.scoring import normalisation
from src.domain.scoring.metric import Metric
from src.domain.scoring.metric_spec import METRIC_SPECS
from src.domain.session import Session


def build_metrics(session: Session, evidences: Sequence[Evidence]) -> list[Metric]:
    """Compute the M4 metric catalogue; omit metrics with no supporting evidence (R10)."""
    del session
    by_criterion = {evidence.criterion: evidence for evidence in evidences}
    metrics: list[Metric] = []

    agent = by_criterion.get("agent_turns")
    user = by_criterion.get("user_turns")
    if agent is not None and user is not None:
        engaged = (agent.value or 0) > 0 and (user.value or 0) > 0
        metrics.append(
            Metric(
                code="engagement",
                dimension=Dimension.CONVERSATIONAL,
                raw_value=1.0 if engaged else 0.0,
                normalized_score=normalisation.binary(engaged),
                weight=3.0,
                unit="bool",
            )
        )

    duration = by_criterion.get("session_duration_seconds")
    if duration is not None and duration.value is not None:
        metrics.append(
            Metric(
                code="duration",
                dimension=Dimension.TECHNICAL,
                raw_value=duration.value,
                normalized_score=normalisation.latency(duration.value, optimal=300, degraded=900),
                weight=1.0,
                unit="seconds",
            )
        )

    for spec in METRIC_SPECS:
        evidence = by_criterion.get(spec.criterion)
        if evidence is None or evidence.value is None:
            continue
        metrics.append(
            Metric(
                code=spec.code,
                dimension=spec.dimension,
                raw_value=evidence.value,
                normalized_score=spec.normalize(spec.transform(evidence.value)),
                weight=spec.weight,
                unit=spec.unit,
            )
        )

    return metrics
