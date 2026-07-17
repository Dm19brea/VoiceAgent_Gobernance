"""PR3 — POST /agents/{agent_id}/activate and /deactivate endpoints."""

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.auth import require_auth
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository
from src.main import app
from tests.conftest import insert_governed_agent


async def test_activate_sets_webhook_activated_true(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent = await insert_governed_agent(db_session, "va-act-1", webhook_activated=False)

    response = await client.post(f"/agents/{agent.agent_id}/activate")

    assert response.status_code == 200
    assert response.json()["webhook_activated"] is True


async def test_activate_is_idempotent(client: AsyncClient, db_session: AsyncSession) -> None:
    agent = await insert_governed_agent(db_session, "va-act-2", webhook_activated=True)

    response = await client.post(f"/agents/{agent.agent_id}/activate")

    assert response.status_code == 200
    assert response.json()["webhook_activated"] is True


async def test_deactivate_sets_webhook_activated_false(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent = await insert_governed_agent(db_session, "va-deact-1", webhook_activated=True)

    response = await client.post(f"/agents/{agent.agent_id}/deactivate")

    assert response.status_code == 200
    assert response.json()["webhook_activated"] is False


async def test_deactivate_is_idempotent(client: AsyncClient, db_session: AsyncSession) -> None:
    agent = await insert_governed_agent(db_session, "va-deact-2", webhook_activated=False)

    response = await client.post(f"/agents/{agent.agent_id}/deactivate")

    assert response.status_code == 200
    assert response.json()["webhook_activated"] is False


async def test_activate_unknown_agent_returns_404(client: AsyncClient) -> None:
    response = await client.post(f"/agents/{uuid4()}/activate")

    assert response.status_code == 404


async def test_deactivate_unknown_agent_returns_404(client: AsyncClient) -> None:
    response = await client.post(f"/agents/{uuid4()}/deactivate")

    assert response.status_code == 404


async def test_activate_soft_deleted_agent_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent = await insert_governed_agent(db_session, "va-act-del", webhook_activated=False)
    delete_response = await client.delete(f"/agents/{agent.agent_id}")
    assert delete_response.status_code == 204

    response = await client.post(f"/agents/{agent.agent_id}/activate")

    assert response.status_code == 404


async def test_deactivate_soft_deleted_agent_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent = await insert_governed_agent(db_session, "va-deact-del", webhook_activated=True)
    delete_response = await client.delete(f"/agents/{agent.agent_id}")
    assert delete_response.status_code == 204

    response = await client.post(f"/agents/{agent.agent_id}/deactivate")

    assert response.status_code == 404


async def test_activate_unauthenticated_returns_401_and_does_not_mutate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent = await insert_governed_agent(db_session, "va-act-noauth", webhook_activated=False)
    app.dependency_overrides.pop(require_auth, None)

    response = await client.post(f"/agents/{agent.agent_id}/activate")

    assert response.status_code == 401
    repository = SqlAlchemyGovernanceRepository(db_session)
    stored = await repository.get_agent_by_assistant_id("va-act-noauth")
    assert stored is not None
    assert stored.webhook_activated is False


async def test_deactivate_unauthenticated_returns_401_and_does_not_mutate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent = await insert_governed_agent(db_session, "va-deact-noauth", webhook_activated=True)
    app.dependency_overrides.pop(require_auth, None)

    response = await client.post(f"/agents/{agent.agent_id}/deactivate")

    assert response.status_code == 401
    repository = SqlAlchemyGovernanceRepository(db_session)
    stored = await repository.get_agent_by_assistant_id("va-deact-noauth")
    assert stored is not None
    assert stored.webhook_activated is True
