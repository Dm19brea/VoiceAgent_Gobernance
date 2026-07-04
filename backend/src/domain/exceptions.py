class DomainError(Exception):
    """Base class for domain rule violations."""


class SessionClosedError(DomainError):
    """Raised when an event is recorded on a session that is no longer active."""
