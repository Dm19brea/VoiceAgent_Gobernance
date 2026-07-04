from typing import Any

from src.adapters.rest.vapi_mapping import map_vapi_event
from src.domain.enums import EventType, Source


def _webhook(message: dict[str, Any]) -> dict[str, Any]:
    base = {"type": message["type"], "call": {"id": "call-1", "assistantId": "asst-1"}}
    return {"message": {**base, **message}}


def test_maps_status_update_in_progress_to_session_started() -> None:
    result = map_vapi_event(_webhook({"type": "status-update", "status": "in-progress"}))

    assert result is not None
    assert result.call_id == "call-1"
    assert result.assistant_id == "asst-1"
    assert result.event_type is EventType.SESSION_STARTED
    assert result.source is Source.PLATFORM


def test_maps_end_of_call_report_to_session_ended() -> None:
    result = map_vapi_event(_webhook({"type": "end-of-call-report"}))

    assert result is not None
    assert result.event_type is EventType.SESSION_ENDED
    assert result.source is Source.PLATFORM


def test_maps_assistant_speech_to_agent_response() -> None:
    result = map_vapi_event(_webhook({"type": "speech-update", "role": "assistant"}))

    assert result is not None
    assert result.event_type is EventType.CONVERSATION_AGENT_RESPONSE
    assert result.source is Source.AGENT


def test_maps_user_speech_to_user_input() -> None:
    result = map_vapi_event(_webhook({"type": "speech-update", "role": "user"}))

    assert result is not None
    assert result.event_type is EventType.CONVERSATION_USER_INPUT
    assert result.source is Source.USER


def test_unknown_type_is_not_promoted() -> None:
    result = map_vapi_event(_webhook({"type": "phone-call-control"}))

    assert result is None
