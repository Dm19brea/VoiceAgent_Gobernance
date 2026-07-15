"""PR1 — POST /agents register/upsert endpoint (S1, S2, S5)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.agent_routes import get_assistant_directory
from src.domain.agent import Agent
from src.domain.enums import AgentStatus
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository
from src.main import app
from tests.fakes import FakeAssistantDirectory


async def test_register_creates_new_agent(client: AsyncClient) -> None:
    response = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-1", "name": "Citas", "objective": "Confirmar"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["vapi_assistant_id"] == "va-1"
    assert body["name"] == "Citas"
    assert body["objective"] == "Confirmar"
    assert body["status"] == "active"
    assert "agent_id" in body


async def test_register_promotes_unregistered_agent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    repo = SqlAlchemyGovernanceRepository(db_session)
    unregistered = Agent(
        name="Unregistered va-2",
        objective="(unregistered)",
        vapi_assistant_id="va-2",
        status=AgentStatus.UNREGISTERED,
    )
    await repo.add_agent(unregistered)
    await db_session.commit()

    response = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-2", "name": "Citas", "objective": "Confirmar"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == str(unregistered.agent_id)
    assert body["status"] == "active"
    assert body["name"] == "Citas"


async def test_register_rejects_blank_vapi_assistant_id(client: AsyncClient) -> None:
    response = await client.post(
        "/agents",
        json={"vapi_assistant_id": " ", "name": "Citas", "objective": "Confirmar"},
    )

    assert response.status_code == 422


async def test_register_rejects_blank_name(client: AsyncClient) -> None:
    response = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-3", "name": " ", "objective": "Confirmar"},
    )

    assert response.status_code == 422


async def test_register_rejects_blank_objective(client: AsyncClient) -> None:
    response = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-4", "name": "Citas", "objective": ""},
    )

    assert response.status_code == 422


async def test_list_agents_returns_empty_list(client: AsyncClient) -> None:
    response = await client.get("/agents")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_agents_returns_mixed_statuses(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PR2 — GET /agents (R10-R11, S6)."""
    repo = SqlAlchemyGovernanceRepository(db_session)
    unregistered = Agent(
        name="Unregistered va-5",
        objective="(unregistered)",
        vapi_assistant_id="va-5",
        status=AgentStatus.UNREGISTERED,
    )
    await repo.add_agent(unregistered)
    await db_session.commit()

    await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-6", "name": "Citas", "objective": "Confirmar"},
    )

    response = await client.get("/agents")

    assert response.status_code == 200
    body = {agent["vapi_assistant_id"]: agent for agent in response.json()}
    assert body["va-5"]["status"] == "unregistered"
    assert body["va-6"]["status"] == "active"
    assert body["va-6"]["name"] == "Citas"


async def test_register_existing_assistant_returns_active_agent(client: AsyncClient) -> None:
    """R1 S1 — assistant verified to exist in Vapi → 200 ACTIVE, persisted."""
    directory = FakeAssistantDirectory(exists=True)
    app.dependency_overrides[get_assistant_directory] = lambda: directory

    response = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-exists", "name": "Citas", "objective": "Confirmar"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["vapi_assistant_id"] == "va-exists"
    assert directory.calls == ["va-exists"]


async def test_register_nonexistent_assistant_returns_422_and_persists_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """R1 S2 — assistant not found in Vapi → 422, no agent row created."""
    directory = FakeAssistantDirectory(exists=False)
    app.dependency_overrides[get_assistant_directory] = lambda: directory

    response = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-missing", "name": "Citas", "objective": "Confirmar"},
    )

    assert response.status_code == 422
    assert directory.calls == ["va-missing"]
    repo = SqlAlchemyGovernanceRepository(db_session)
    assert await repo.get_agent_by_assistant_id("va-missing") is None


async def test_register_when_vapi_unavailable_returns_502_and_persists_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """R1 S3 — Vapi unreachable/erroring → 502 (fail-closed), no agent row created."""
    directory = FakeAssistantDirectory(unavailable=True)
    app.dependency_overrides[get_assistant_directory] = lambda: directory

    response = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-down", "name": "Citas", "objective": "Confirmar"},
    )

    assert response.status_code == 502
    assert directory.calls == ["va-down"]
    repo = SqlAlchemyGovernanceRepository(db_session)
    assert await repo.get_agent_by_assistant_id("va-down") is None


async def test_register_calls_directory_with_submitted_assistant_id(client: AsyncClient) -> None:
    """R1 S4 — the directory is invoked with the exact submitted id."""
    directory = FakeAssistantDirectory(exists=True)
    app.dependency_overrides[get_assistant_directory] = lambda: directory

    await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-precise-id", "name": "Citas", "objective": "Confirmar"},
    )

    assert directory.calls == ["va-precise-id"]


async def test_delete_existing_agent_removes_it_from_list(client: AsyncClient) -> None:
    """R2 S5 — DELETE an existing agent succeeds and it disappears from GET /agents."""
    created = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-del-1", "name": "Citas", "objective": "Confirmar"},
    )
    agent_id = created.json()["agent_id"]

    response = await client.delete(f"/agents/{agent_id}")

    assert response.status_code == 204
    listed = await client.get("/agents")
    assert all(agent["agent_id"] != agent_id for agent in listed.json())


async def test_delete_nonexistent_agent_returns_404(client: AsyncClient) -> None:
    """R2 S6 — DELETE an agent_id that never existed returns 404."""
    from uuid import uuid4

    response = await client.delete(f"/agents/{uuid4()}")

    assert response.status_code == 404


async def test_delete_already_deleted_agent_returns_404(client: AsyncClient) -> None:
    """R2 S6 — repeated DELETE is a not-found error, not idempotent-success."""
    created = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-del-2", "name": "Citas", "objective": "Confirmar"},
    )
    agent_id = created.json()["agent_id"]
    first = await client.delete(f"/agents/{agent_id}")
    assert first.status_code == 204

    second = await client.delete(f"/agents/{agent_id}")

    assert second.status_code == 404


async def test_reregistering_soft_deleted_assistant_reactivates_single_row(
    client: AsyncClient,
) -> None:
    """R2b S9 — re-registering a soft-deleted vapi_assistant_id reactivates it."""
    created = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-reactivate", "name": "Citas", "objective": "Confirmar"},
    )
    agent_id = created.json()["agent_id"]
    delete_response = await client.delete(f"/agents/{agent_id}")
    assert delete_response.status_code == 204

    reregistered = await client.post(
        "/agents",
        json={"vapi_assistant_id": "va-reactivate", "name": "Citas 2", "objective": "Confirmar 2"},
    )

    assert reregistered.status_code == 200
    body = reregistered.json()
    assert body["agent_id"] == agent_id
    assert body["status"] == "active"
    assert body["name"] == "Citas 2"

    listed = await client.get("/agents")
    matches = [agent for agent in listed.json() if agent["agent_id"] == agent_id]
    assert len(matches) == 1
