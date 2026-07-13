"""Blocking flags: conditions that force result = failed regardless of score (design D4, R5).

Detection is pure and deterministic.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.evidence import Evidence

FLAG_SESSION_NOT_COMPLETED = "session_not_completed"
FLAG_SESSION_FAILED = "session_failed"
FLAG_GOAL_NOT_COMPLETED = "goal_not_completed"
FLAG_UNRECOVERED_ERROR = "unrecovered_error"


@dataclass(frozen=True, slots=True)
class BlockingFlag:
    """A blocking condition and the human-readable reason it fired (R5)."""

    code: str
    reason: str


def detect_blocking_flags(evidences: Sequence[Evidence]) -> list[BlockingFlag]:
    """Return the active blocking flags for a session's evidences."""
    flags: list[BlockingFlag] = []
    criteria = {evidence.criterion for evidence in evidences}
    by_criterion = {evidence.criterion: evidence for evidence in evidences}

    if "session_failed" in criteria:
        flags.append(
            BlockingFlag(
                code=FLAG_SESSION_FAILED,
                reason="The session ended with an uncontrolled error.",
            )
        )
    elif "session_completed" not in criteria:
        flags.append(
            BlockingFlag(
                code=FLAG_SESSION_NOT_COMPLETED,
                reason="The session did not record a completion event.",
            )
        )

    goal_completion = by_criterion.get("goal_completion")
    if (
        goal_completion is not None
        and goal_completion.value is not None
        and goal_completion.value < 0.5
    ):
        flags.append(
            BlockingFlag(
                code=FLAG_GOAL_NOT_COMPLETED,
                reason="The session did not reach its conversational goal.",
            )
        )

    unrecovered_error = by_criterion.get("unrecovered_error_present")
    if (
        unrecovered_error is not None
        and unrecovered_error.value is not None
        and unrecovered_error.value >= 0.5
    ):
        flags.append(
            BlockingFlag(
                code=FLAG_UNRECOVERED_ERROR,
                reason="The session ended with an unrecovered technical error.",
            )
        )

    return flags
