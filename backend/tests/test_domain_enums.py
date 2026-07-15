from src.domain.enums import (
    AgentStatus,
    Dimension,
    EventType,
    EvidenceType,
    SessionStatus,
    Source,
)


def test_event_type_values_include_doc_31_taxonomy() -> None:
    expected = {
        "session.started",
        "session.ended",
        "session.failed",
        "session.evaluation_triggered",
        "conversation.turn_started",
        "conversation.turn_ended",
        "conversation.agent_response",
        "conversation.user_input",
        "conversation.silence_detected",
        "conversation.interruption_detected",
        "conversation.topic_change",
        "conversation.goal_achieved",
        "conversation.goal_failed",
        "system.latency_measured",
        "system.model_invocation",
        "system.error",
        "system.warning",
        "system.flag_raised",
    }

    assert {event_type.value for event_type in EventType} == expected


def test_source_values() -> None:
    assert {source.value for source in Source} == {
        "agent",
        "user",
        "platform",
        "system",
    }


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
