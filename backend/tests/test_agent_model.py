"""PR1 (agent-webhook-activation) — AgentModel.webhook_activated column."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.models import AgentModel


def test_agent_model_has_webhook_activated_column() -> None:
    columns = AgentModel.__table__.columns

    assert "webhook_activated" in columns
    assert columns["webhook_activated"].nullable is False


async def test_agent_model_webhook_activated_defaults_false_via_create_all(
    db_session: AsyncSession,
) -> None:
    """Schema built via ``Base.metadata.create_all`` must default the column
    to ``false`` through ``server_default`` (not only the ORM default), since
    the test schema is never built via Alembic."""
    row = AgentModel(
        agent_id="11111111-1111-1111-1111-111111111111",
        name="Citas",
        objective="Confirmar",
        vapi_assistant_id="asst-model-default",
        status="active",
    )
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)

    assert row.webhook_activated is False
