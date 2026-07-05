from typing import Any

from src.adapters.rest.vapi_mapping import map_vapi_event


def _end_of_call(message: dict[str, Any]) -> dict[str, Any]:
    base = {"type": "end-of-call-report", "call": {"id": "call-1", "assistantId": "asst-1"}}
    return {"message": {**base, **message}}


def test_normalises_end_of_call_report_fields() -> None:
    result = map_vapi_event(
        _end_of_call(
            {
                "endedReason": "customer-ended-call",
                "durationSeconds": 42,
                "summary": "The appointment was confirmed.",
            }
        )
    )

    assert result is not None
    report = result.payload["report"]
    assert report["ended_reason"] == "customer-ended-call"
    assert report["duration_seconds"] == 42
    assert report["summary"] == "The appointment was confirmed."


def test_report_is_present_but_empty_when_fields_absent() -> None:
    result = map_vapi_event(_end_of_call({}))

    assert result is not None
    report = result.payload["report"]
    assert report["ended_reason"] is None
    assert report["duration_seconds"] is None
