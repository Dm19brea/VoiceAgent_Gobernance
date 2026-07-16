"""Security hardening S1 — redact raw third-party payload from EventOut.

``Event.payload`` retains the full raw Vapi message (governance provenance),
but the API response must only ever expose the allowlisted keys the dashboard
actually renders (see ``buildTranscript.ts``).
"""

from datetime import UTC, datetime
from typing import Any

from src.adapters.rest.query_routes import _to_event_out
from src.domain.enums import EventType, Source
from src.domain.event import Event

TIMESTAMP = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def _event(payload: dict[str, Any]) -> Event:
    return Event(
        session_id="call-a",
        event_type=EventType.CONVERSATION_AGENT_RESPONSE,
        source=Source.AGENT,
        sequence_number=1,
        timestamp=TIMESTAMP,
        payload=payload,
    )


def test_event_out_strips_raw_provider_fields_keeps_allowlisted_turn_keys() -> None:
    raw_payload = {
        "content": "Claro, confirmo su cita.",
        "role": "assistant",
        "turn_index": 0,
        "recordingUrl": "https://storage.vapi.ai/recording-secret.wav",
        "stereoRecordingUrl": "https://storage.vapi.ai/stereo-secret.wav",
        "transcript": "full raw transcript blob",
        "summary": "raw call summary",
        "call": {"id": "call-a", "customer": {"number": "+34600000000"}},
        "assistant": {"id": "asst-1", "orgId": "org-secret"},
    }

    out = _to_event_out(_event(raw_payload))

    assert out.payload["content"] == "Claro, confirmo su cita."
    assert out.payload["role"] == "assistant"
    assert out.payload["turn_index"] == 0
    for leaked_key in (
        "recordingUrl",
        "stereoRecordingUrl",
        "transcript",
        "summary",
        "call",
        "assistant",
    ):
        assert leaked_key not in out.payload


def test_event_out_keeps_allowlisted_silence_keys() -> None:
    raw_payload = {
        "count": 1,
        "threshold_ms": 3000,
        "detector_version": "v1",
        "intervals": [{"user_turn_index": 0, "duration_ms": 4200}],
        "orgId": "org-secret",
    }

    out = _to_event_out(_event(raw_payload))

    assert out.payload["count"] == 1
    assert out.payload["threshold_ms"] == 3000
    assert out.payload["detector_version"] == "v1"
    assert out.payload["intervals"] == [{"user_turn_index": 0, "duration_ms": 4200}]
    assert "orgId" not in out.payload


def test_event_out_drops_unknown_keys_entirely_when_payload_has_none_allowlisted() -> None:
    out = _to_event_out(_event({"providerOnly": "leak"}))

    assert out.payload == {}
