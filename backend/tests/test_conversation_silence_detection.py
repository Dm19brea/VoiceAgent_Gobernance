import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from src.application.use_cases.detect_conversation_silence import (
    DEFAULT_SILENCE_POLICY,
    SILENCE_DETECTOR_VERSION,
    SILENCE_THRESHOLD_MS,
    SilencePolicy,
    TimedTurn,
    detect_user_response_silence,
)

BASE = datetime(2026, 7, 11, tzinfo=UTC)


def _turn(
    role: str,
    index: int,
    started_ms: float | None,
    ended_ms: float | None,
) -> TimedTurn:
    def at(offset: float | None) -> datetime | None:
        return None if offset is None else BASE + timedelta(milliseconds=offset)

    return TimedTurn(
        role=role,
        turn_index=index,
        started_at=at(started_ms),
        ended_at=at(ended_ms),
    )


@pytest.mark.parametrize(
    ("gap_ms", "expected_count"),
    [(5999, 0), (6000, 1), (7001, 1)],
)
def test_inclusive_threshold_boundary(gap_ms: int, expected_count: int) -> None:
    turns = (
        _turn("assistant", 0, 0, 1000),
        _turn("user", 1, 1000 + gap_ms, 9000),
    )

    result = detect_user_response_silence(turns)

    assert (0 if result is None else result.count) == expected_count


def test_only_direct_assistant_to_user_transitions_qualify() -> None:
    turns = (
        _turn("user", 0, 0, 1000),
        _turn("assistant", 1, 9000, 10000),
        _turn("assistant", 2, 11000, 12000),
        _turn("user", 3, 18000, 19000),
    )

    result = detect_user_response_silence(turns)

    assert result is not None
    assert [(item.assistant_turn_index, item.user_turn_index) for item in result.intervals] == [
        (2, 3)
    ]


def test_terminal_and_pre_or_post_call_silence_are_absent_by_construction() -> None:
    turns = (
        _turn("user", 0, 10000, 11000),
        _turn("assistant", 1, 12000, 13000),
    )

    assert detect_user_response_silence(turns) is None


@pytest.mark.parametrize(
    "turns",
    [
        (_turn("assistant", 0, 0, None), _turn("user", 1, 8000, 9000)),
        (_turn("assistant", 0, 0, 1000), _turn("user", 1, None, 9000)),
        (_turn("assistant", 0, 0, 9000), _turn("user", 1, 8000, 10000)),
        (_turn("assistant", 0, 2000, 1000), _turn("user", 1, 8000, 9000)),
        (_turn("assistant", -1, 0, 1000), _turn("user", 1, 8000, 9000)),
        (_turn("assistant", 2, 0, 1000), _turn("user", 1, 8000, 9000)),
    ],
)
def test_invalid_or_inconsistent_boundaries_fail_closed(
    turns: tuple[TimedTurn, TimedTurn],
) -> None:
    assert detect_user_response_silence(turns) is None


def test_non_finite_datetime_like_values_fail_closed() -> None:
    malformed = TimedTurn(
        role="assistant",
        turn_index=0,
        started_at=BASE,
        ended_at=cast(Any, float("nan")),
    )
    user = _turn("user", 1, 8000, 9000)

    assert detect_user_response_silence((malformed, user)) is None


def test_pre_epoch_boundary_fails_closed() -> None:
    assistant = TimedTurn(
        role="assistant",
        turn_index=0,
        started_at=datetime(1969, 12, 31, 23, 59, 58, tzinfo=UTC),
        ended_at=datetime(1969, 12, 31, 23, 59, 59, tzinfo=UTC),
    )
    user = TimedTurn(
        role="user",
        turn_index=1,
        started_at=datetime(1970, 1, 1, 0, 0, 6, tzinfo=UTC),
        ended_at=datetime(1970, 1, 1, 0, 0, 7, tzinfo=UTC),
    )

    assert detect_user_response_silence((assistant, user)) is None


def test_multiple_gaps_are_aggregated_chronologically() -> None:
    turns = (
        _turn("assistant", 0, 0, 1000),
        _turn("user", 1, 7000, 8000),
        _turn("assistant", 2, 9000, 10000),
        _turn("user", 3, 18000, 19000),
        _turn("assistant", 4, 20000, 21000),
        _turn("user", 5, 32000, 33000),
    )

    result = detect_user_response_silence(turns)

    assert result is not None
    assert result.count == 3
    assert result.count == len(result.intervals)
    assert [item.duration_ms for item in result.intervals] == [6000, 8000, 11000]
    assert [item.assistant_turn_index for item in result.intervals] == [0, 2, 4]
    assert result.detected_at == BASE + timedelta(milliseconds=32000)
    assert result.detected_at == result.intervals[-1].ended_at


def test_valid_gap_survives_an_untrustworthy_candidate() -> None:
    turns = (
        _turn("assistant", 0, 0, None),
        _turn("user", 1, 8000, 9000),
        _turn("assistant", 2, 10000, 11000),
        _turn("user", 3, 17000, 18000),
    )

    result = detect_user_response_silence(turns)

    assert result is not None
    assert result.count == 1
    assert result.intervals[0].duration_ms == 6000


def test_policy_and_results_are_immutable_and_versioned() -> None:
    assert (
        SilencePolicy(
            threshold_ms=6000,
            detector_version="assistant-user-interior-gap/v1",
        )
        == DEFAULT_SILENCE_POLICY
    )
    assert SILENCE_THRESHOLD_MS == 6000
    assert SILENCE_DETECTOR_VERSION == "assistant-user-interior-gap/v1"

    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_SILENCE_POLICY.threshold_ms = 1  # type: ignore[misc]


def test_turn_interval_and_aggregate_results_are_immutable() -> None:
    assistant = _turn("assistant", 0, 0, 1000)
    user = _turn("user", 1, 7000, 8000)
    result = detect_user_response_silence((assistant, user))

    assert result is not None
    interval = result.intervals[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        assistant.turn_index = 2  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        interval.duration_ms = 1  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.count = 0  # type: ignore[misc]


@pytest.mark.parametrize(
    "policy",
    [
        SilencePolicy(threshold_ms=0, detector_version="v1"),
        SilencePolicy(threshold_ms=-1, detector_version="v1"),
        SilencePolicy(threshold_ms=6000, detector_version=""),
    ],
)
def test_invalid_policy_is_rejected(policy: SilencePolicy) -> None:
    with pytest.raises(ValueError):
        detect_user_response_silence((), policy)
