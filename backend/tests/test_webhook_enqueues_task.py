import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class _FakeTask:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def delay(self, session_id: str) -> None:
        self.calls.append(session_id)


async def test_webhook_enqueues_evidence_task_on_session_ended(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeTask()
    monkeypatch.setattr("src.adapters.rest.vapi.build_session_evidences", fake)

    call = {"id": "call-e", "assistantId": "asst-e"}
    started = {"message": {"type": "status-update", "status": "in-progress", "call": call}}
    ended = {"message": {"type": "end-of-call-report", "call": call}}

    await client.post("/webhooks/vapi", json=started)
    response = await client.post("/webhooks/vapi", json=ended)

    assert response.status_code == 200
    assert fake.calls == ["call-e"]
