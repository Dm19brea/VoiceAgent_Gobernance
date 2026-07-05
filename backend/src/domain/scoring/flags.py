"""Blocking flags: conditions that force result = failed regardless of score (design D4, R5).

Detection is pure and deterministic. M4 detects the conditions observable now; more flags
(e.g. ``session_failed``) plug in here as the events that reveal them are captured.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.evidence import Evidence

FLAG_SESSION_NOT_COMPLETED = "session_not_completed"


@dataclass(frozen=True, slots=True)
class BlockingFlag:
    """A blocking condition and the human-readable reason it fired (R5)."""

    code: str
    reason: str


def detect_blocking_flags(evidences: Sequence[Evidence]) -> list[BlockingFlag]:
    """Return the active blocking flags for a session's evidences."""
    flags: list[BlockingFlag] = []
    criteria = {evidence.criterion for evidence in evidences}

    if "session_completed" not in criteria:
        flags.append(
            BlockingFlag(
                code=FLAG_SESSION_NOT_COMPLETED,
                reason="The session did not record a completion event.",
            )
        )

    return flags
