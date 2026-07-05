from src.domain.enums import (
    AgentStatus,
    Dimension,
    EventType,
    EvidenceType,
    SessionStatus,
    Source,
)


def test_event_type_values() -> None:
    assert EventType.SESSION_STARTED.value == "session.started"
    assert EventType.SESSION_ENDED.value == "session.ended"
    assert EventType.CONVERSATION_AGENT_RESPONSE.value == "conversation.agent_response"
    assert EventType.CONVERSATION_USER_INPUT.value == "conversation.user_input"


def test_source_values() -> None:
    assert Source.AGENT.value == "agent"
    assert Source.USER.value == "user"
    assert Source.PLATFORM.value == "platform"


def test_session_status_values() -> None:
    assert SessionStatus.ACTIVE.value == "active"
    assert SessionStatus.ENDED.value == "ended"
    assert SessionStatus.FAILED.value == "failed"


def test_agent_status_values() -> None:
    assert AgentStatus.ACTIVE.value == "active"
    assert AgentStatus.UNREGISTERED.value == "unregistered"


def test_evidence_type_values() -> None:
    assert EvidenceType.DIRECT.value == "direct"
    assert EvidenceType.INFERRED.value == "inferred"
    assert EvidenceType.COMPOSITE.value == "composite"


def test_dimension_values() -> None:
    assert Dimension.CONVERSATIONAL.value == "conversational"
    assert Dimension.OPERATIONAL.value == "operational"
    assert Dimension.TECHNICAL.value == "technical"
    assert Dimension.RISK.value == "risk"
