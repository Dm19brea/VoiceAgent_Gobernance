from enum import StrEnum


class EventType(StrEnum):
    """Canonical governance event taxonomy from document 3.1."""

    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"
    SESSION_FAILED = "session.failed"
    SESSION_EVALUATION_TRIGGERED = "session.evaluation_triggered"

    CONVERSATION_TURN_STARTED = "conversation.turn_started"
    CONVERSATION_TURN_ENDED = "conversation.turn_ended"
    CONVERSATION_AGENT_RESPONSE = "conversation.agent_response"
    CONVERSATION_USER_INPUT = "conversation.user_input"
    CONVERSATION_SILENCE_DETECTED = "conversation.silence_detected"
    CONVERSATION_INTERRUPTION_DETECTED = "conversation.interruption_detected"
    CONVERSATION_TOPIC_CHANGE = "conversation.topic_change"
    CONVERSATION_GOAL_ACHIEVED = "conversation.goal_achieved"
    CONVERSATION_GOAL_FAILED = "conversation.goal_failed"

    TOOL_CALLED = "tool.called"
    TOOL_RESPONSE_RECEIVED = "tool.response_received"
    TOOL_FAILED = "tool.failed"
    TOOL_TIMEOUT = "tool.timeout"
    TOOL_RETRY = "tool.retry"

    SYSTEM_LATENCY_MEASURED = "system.latency_measured"
    SYSTEM_MODEL_INVOCATION = "system.model_invocation"
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"
    SYSTEM_FLAG_RAISED = "system.flag_raised"


class Source(StrEnum):
    AGENT = "agent"
    USER = "user"
    PLATFORM = "platform"
    SYSTEM = "system"
    TOOL = "tool"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"
    FAILED = "failed"


class AgentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNDER_VALIDATION = "under_validation"
    UNREGISTERED = "unregistered"


class EvidenceType(StrEnum):
    DIRECT = "direct"
    INFERRED = "inferred"
    COMPOSITE = "composite"


class Dimension(StrEnum):
    CONVERSATIONAL = "conversational"
    OPERATIONAL = "operational"
    TECHNICAL = "technical"
    RISK = "risk"


class EvaluationResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
