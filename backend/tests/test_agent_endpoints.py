"""PR1 — POST /agents register/upsert endpoint (S1, S2, S5)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import AgentStatus
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository


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
