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


def _turns(session_id: str, criterion: str, label: str, events: list[Event]) -> Evidence:
    return Evidence(
        session_id=session_id,
        evidence_type=EvidenceType.INFERRED,
        criterion=criterion,
        conclusion=f"The session had {len(events)} {label}",
        dimension=Dimension.CONVERSATIONAL,
        source_events=[e.event_id for e in events],
        value=float(len(events)),
    )
