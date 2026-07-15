"""Application-level errors shared across use cases."""


class AssistantNotFoundError(Exception):
    """Raised when a submitted ``vapi_assistant_id`` does not exist in Vapi."""

    def __init__(self, assistant_id: str) -> None:
        super().__init__(f"Vapi assistant not found: {assistant_id}")
        self.assistant_id = assistant_id
