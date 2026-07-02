from typing import Any

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

VALID_EVENT: dict[str, Any] = {
    "event_type": "call.started",
    "agent_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-06-29T10:05:00Z",
    "source": "agent",
}


def test_post_events_accepts_valid_event() -> None:
    response = client.post("/events", json=VALID_EVENT)

    assert response.status_code == 202
    assert response.json()["event_type"] == "call.started"


def test_post_events_rejects_missing_agent_id() -> None:
    payload = {k: v for k, v in VALID_EVENT.items() if k != "agent_id"}

    response = client.post("/events", json=payload)

    assert response.status_code == 422
