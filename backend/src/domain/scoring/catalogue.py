"""M4 metric catalogue: compute metrics from a session's evidences (doc 3.3, design D2).

Pure and deterministic. Metrics whose source evidence is absent are omitted, never
faked (R10). The categorical ``clean_ending`` reads the session's normalised report
(the ``session.ended`` event payload), keeping the domain free of Vapi specifics.
"""

from collections.abc import Sequence

from src.domain.enums import Dimension, EventType
from src.domain.evidence import Evidence
from src.domain.scoring import normalisation
from src.domain.scoring.metric import Metric
from src.domain.session import Session

# Terminal reasons that mean the call did not end cleanly. Any reason mentioning an
# error or failure is also treated as unclean (covers Vapi's pipeline-error-* family).
BAD_ENDED_REASONS = frozenset(
    {
        "customer-did-not-answer",
        "silence-timed-out",
        "exceeded-max-duration",
        "assistant-not-found",
        "no-server-available",
    }
)


def build_metrics(session: Session, evidences: Sequence[Evidence]) -> list[Metric]:
    """Compute the M4 metric catalogue; omit metrics with no supporting evidence (R10)."""
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

    if "session_completed" in by_criterion:
        metrics.append(
            Metric(
                code="completion",
                dimension=Dimension.TECHNICAL,
                raw_value=1.0,
                normalized_score=normalisation.binary(1),
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

    reason = _ended_reason(session)
    if reason is not None:
        clean = _is_clean_ending(reason)
        metrics.append(
            Metric(
                code="clean_ending",
                dimension=Dimension.RISK,
                raw_value=1.0 if clean else 0.0,
                normalized_score=normalisation.binary(clean),
                weight=3.0,
                unit="bool",
            )
        )

    return metrics


def _ended_reason(session: Session) -> str | None:
    for event in reversed(session.events):
        if event.event_type is EventType.SESSION_ENDED:
            report = event.payload.get("report") or {}
            return report.get("ended_reason")
    return None


def _is_clean_ending(reason: str) -> bool:
    lowered = reason.lower()
    if "error" in lowered or "failed" in lowered:
        return False
    return reason not in BAD_ENDED_REASONS
