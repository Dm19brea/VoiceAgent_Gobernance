"""Provider-independent detection of prolonged user-response silence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite

SILENCE_THRESHOLD_MS = 6000
SILENCE_DETECTOR_VERSION = "assistant-user-interior-gap/v1"


@dataclass(frozen=True, slots=True)
class SilencePolicy:
    threshold_ms: int = SILENCE_THRESHOLD_MS
    detector_version: str = SILENCE_DETECTOR_VERSION


DEFAULT_SILENCE_POLICY = SilencePolicy()


@dataclass(frozen=True, slots=True)
class TimedTurn:
    role: str
    turn_index: int
    started_at: datetime | None
    ended_at: datetime | None


@dataclass(frozen=True, slots=True)
class SilenceInterval:
    assistant_turn_index: int
    user_turn_index: int
    started_at: datetime
    ended_at: datetime
    duration_ms: float


@dataclass(frozen=True, slots=True)
class SilenceAggregate:
    count: int
    intervals: tuple[SilenceInterval, ...]
    detected_at: datetime


def detect_user_response_silence(
    turns: Iterable[TimedTurn],
    policy: SilencePolicy = DEFAULT_SILENCE_POLICY,
) -> SilenceAggregate | None:
    """Aggregate qualifying adjacent assistant-to-user response gaps.

    Invalid candidates are ignored rather than inferred. This lets one malformed
    boundary fail closed without hiding other trustworthy intervals.
    """
    _validate_policy(policy)
    ordered_turns = tuple(turns)
    intervals: list[SilenceInterval] = []

    for assistant, user in zip(ordered_turns, ordered_turns[1:], strict=False):
        interval = _qualifying_interval(assistant, user, policy)
        if interval is not None:
            intervals.append(interval)

    intervals.sort(key=lambda interval: (interval.ended_at, interval.user_turn_index))
    if not intervals:
        return None

    immutable_intervals = tuple(intervals)
    return SilenceAggregate(
        count=len(immutable_intervals),
        intervals=immutable_intervals,
        detected_at=immutable_intervals[-1].ended_at,
    )


def _validate_policy(policy: SilencePolicy) -> None:
    if (
        isinstance(policy.threshold_ms, bool)
        or not isinstance(policy.threshold_ms, int)
        or policy.threshold_ms <= 0
    ):
        raise ValueError("Silence threshold must be a positive integer")
    if not isinstance(policy.detector_version, str) or not policy.detector_version.strip():
        raise ValueError("Silence detector version must be non-empty")


def _qualifying_interval(
    assistant: TimedTurn,
    user: TimedTurn,
    policy: SilencePolicy,
) -> SilenceInterval | None:
    if assistant.role != "assistant" or user.role != "user":
        return None
    if not _valid_turn(assistant) or not _valid_turn(user):
        return None
    if user.turn_index <= assistant.turn_index:
        return None

    assert assistant.ended_at is not None
    assert user.started_at is not None
    gap_ms = (user.started_at - assistant.ended_at).total_seconds() * 1000
    if not isfinite(gap_ms) or gap_ms < policy.threshold_ms:
        return None

    return SilenceInterval(
        assistant_turn_index=assistant.turn_index,
        user_turn_index=user.turn_index,
        started_at=assistant.ended_at,
        ended_at=user.started_at,
        duration_ms=gap_ms,
    )


def _valid_turn(turn: TimedTurn) -> bool:
    if isinstance(turn.turn_index, bool) or not isinstance(turn.turn_index, int):
        return False
    if turn.turn_index < 0:
        return False
    if not _valid_boundary(turn.started_at) or not _valid_boundary(turn.ended_at):
        return False
    assert turn.started_at is not None and turn.ended_at is not None
    return turn.started_at <= turn.ended_at


def _valid_boundary(value: object) -> bool:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return False
    try:
        timestamp = value.astimezone(UTC).timestamp()
    except (OverflowError, OSError, ValueError):
        return False
    return isfinite(timestamp) and timestamp >= 0
