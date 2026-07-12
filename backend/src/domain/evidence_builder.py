from uuid import UUID

from src.domain.enums import Dimension, EventType, EvidenceType
from src.domain.event import Event
from src.domain.evidence import Evidence
from src.domain.session import Session

_CONVERSATION_TYPES = (
    EventType.CONVERSATION_AGENT_RESPONSE,
    EventType.CONVERSATION_USER_INPUT,
)

# A session's trace terminates with either a clean ENDED event or a FAILED one;
# both carry the same end-of-call report shape and must feed the same
# terminal-derived evidence (duration, ended_reason, completion).
TERMINAL_EVENT_TYPES = (EventType.SESSION_ENDED, EventType.SESSION_FAILED)


def build_evidences(session: Session) -> list[Evidence]:
    """Turn a session's event trace into structured evidences (pure, deterministic)."""
    events = session.events
    evidences: list[Evidence] = []

    agent_events = [e for e in events if e.event_type is EventType.CONVERSATION_AGENT_RESPONSE]
    user_events = [e for e in events if e.event_type is EventType.CONVERSATION_USER_INPUT]
    conversation_events = [e for e in events if e.event_type in _CONVERSATION_TYPES]

    evidences.append(_turns(session.session_id, "total_turns", "turns", conversation_events))
    evidences.append(_turns(session.session_id, "agent_turns", "agent turns", agent_events))
    evidences.append(_turns(session.session_id, "user_turns", "user turns", user_events))

    goal_achieved_events = [
        e for e in events if e.event_type is EventType.CONVERSATION_GOAL_ACHIEVED
    ]
    goal_failed_events = [e for e in events if e.event_type is EventType.CONVERSATION_GOAL_FAILED]
    goal_source_events = goal_achieved_events or goal_failed_events
    evidences.append(
        Evidence(
            session_id=session.session_id,
            evidence_type=EvidenceType.INFERRED,
            criterion="goal_completion",
            conclusion=(
                "The session reached its goal"
                if goal_achieved_events
                else "The session did not reach its goal"
            ),
            dimension=Dimension.CONVERSATIONAL,
            source_events=[e.event_id for e in goal_source_events],
            value=1.0 if goal_achieved_events else 0.0,
        )
    )

    interruption_events = [
        e for e in events if e.event_type is EventType.CONVERSATION_INTERRUPTION_DETECTED
    ]
    completed_turns = len(agent_events) - len(interruption_events)
    turn_completion_conclusion = (
        "No agent turns were recorded, so turn completion rate cannot be computed"
        if not agent_events
        else f"{completed_turns} of {len(agent_events)} agent turns completed without interruption"
    )
    evidences.append(
        _rate(
            session.session_id,
            criterion="turn_completion_rate",
            conclusion=turn_completion_conclusion,
            numerator=completed_turns,
            denominator=len(agent_events),
            source_events=[e.event_id for e in interruption_events],
        )
    )

    model_invocation_events = [
        e for e in events if e.event_type is EventType.SYSTEM_MODEL_INVOCATION
    ]
    evidences.append(
        _turns(
            session.session_id,
            "model_invocation_count",
            "model invocations",
            model_invocation_events,
            dimension=Dimension.TECHNICAL,
        )
    )

    silence_events = [e for e in events if e.event_type is EventType.CONVERSATION_SILENCE_DETECTED]
    silence_count = silence_events[0].payload.get("count", 0) if silence_events else 0
    total_turns = len(agent_events) + len(user_events)

    error_events = [e for e in events if e.event_type is EventType.SYSTEM_ERROR]
    technical_error_conclusion = (
        "No agent or user turns were recorded, so technical error rate cannot be computed"
        if not total_turns
        else f"{len(error_events)} system errors out of {total_turns} total turns"
    )
    evidences.append(
        _rate(
            session.session_id,
            criterion="technical_error_rate",
            conclusion=technical_error_conclusion,
            numerator=len(error_events),
            denominator=total_turns,
            source_events=[e.event_id for e in error_events],
            dimension=Dimension.TECHNICAL,
        )
    )

    silence_conclusion = (
        "No agent or user turns were recorded, so silence rate cannot be computed"
        if not total_turns
        else f"{silence_count} prolonged silences out of {total_turns} total turns"
    )
    evidences.append(
        _rate(
            session.session_id,
            criterion="prolonged_silence_rate",
            conclusion=silence_conclusion,
            numerator=silence_count,
            denominator=total_turns,
            source_events=[e.event_id for e in silence_events],
        )
    )

    started_events = [e for e in events if e.event_type is EventType.SESSION_STARTED]
    ended_events = [e for e in events if e.event_type in TERMINAL_EVENT_TYPES]

    if session.ended_at is not None:
        duration = (session.ended_at - session.started_at).total_seconds()
        evidences.append(
            Evidence(
                session_id=session.session_id,
                evidence_type=EvidenceType.INFERRED,
                criterion="session_duration_seconds",
                conclusion=f"The session lasted {duration:.0f} seconds",
                dimension=Dimension.TECHNICAL,
                source_events=[e.event_id for e in started_events + ended_events],
                value=duration,
            )
        )

    if ended_events:
        ended = ended_events[-1]
        if ended.event_type is EventType.SESSION_FAILED:
            criterion, conclusion = "session_failed", "The session failed"
        else:
            criterion, conclusion = "session_completed", "The session completed"
        evidences.append(
            Evidence(
                session_id=session.session_id,
                evidence_type=EvidenceType.DIRECT,
                criterion=criterion,
                conclusion=conclusion,
                dimension=Dimension.TECHNICAL,
                source_events=[ended.event_id],
            )
        )
        report = ended.payload.get("report") or {}
        ended_reason = report.get("ended_reason")
        if ended_reason:
            evidences.append(
                Evidence(
                    session_id=session.session_id,
                    evidence_type=EvidenceType.DIRECT,
                    criterion="ended_reason",
                    conclusion=f"The call ended because: {ended_reason}",
                    dimension=Dimension.OPERATIONAL,
                    source_events=[ended.event_id],
                )
            )

    return evidences


def _turns(
    session_id: str,
    criterion: str,
    label: str,
    events: list[Event],
    dimension: Dimension = Dimension.CONVERSATIONAL,
) -> Evidence:
    return Evidence(
        session_id=session_id,
        evidence_type=EvidenceType.INFERRED,
        criterion=criterion,
        conclusion=f"The session had {len(events)} {label}",
        dimension=dimension,
        source_events=[e.event_id for e in events],
        value=float(len(events)),
    )


def _rate(
    session_id: str,
    criterion: str,
    conclusion: str,
    numerator: int,
    denominator: int,
    source_events: list[UUID],
    dimension: Dimension = Dimension.CONVERSATIONAL,
) -> Evidence:
    value = 0.0 if denominator == 0 else numerator / denominator
    return Evidence(
        session_id=session_id,
        evidence_type=EvidenceType.INFERRED,
        criterion=criterion,
        conclusion=conclusion,
        dimension=dimension,
        source_events=source_events,
        value=value,
    )
