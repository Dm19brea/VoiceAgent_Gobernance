from enum import StrEnum


class EventType(StrEnum):
    """Closed canonical taxonomy reachable from observed Vapi traffic (M2)."""

    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"
    CONVERSATION_AGENT_RESPONSE = "conversation.agent_response"
    CONVERSATION_USER_INPUT = "conversation.user_input"


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
