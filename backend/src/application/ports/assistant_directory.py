from typing import Protocol


class AssistantDirectoryUnavailable(Exception):
    """Raised when the assistant's existence cannot be confirmed (fail-closed).

    Covers transport errors, timeouts, and any non-404 error status from the
    upstream Vapi API. Never silently treated as "exists".
    """


class AssistantDirectory(Protocol):
    """Outbound port that verifies a ``vapi_assistant_id`` exists in Vapi.

    Implementations MUST fail closed: any failure to confirm existence
    (timeout, transport error, non-404 error status) raises
    ``AssistantDirectoryUnavailable`` rather than returning ``True``.
    """

    async def exists(self, assistant_id: str) -> bool: ...
