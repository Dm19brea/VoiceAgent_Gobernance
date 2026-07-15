"""Agent registration and listing endpoints (PR1 R1-R9, PR2 R10-R11)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.agent_schemas import AgentOut, RegisterAgentIn
from src.adapters.vapi.assistant_directory import VapiAssistantDirectory
from src.application.errors import AssistantNotFoundError
from src.application.ports.assistant_directory import (
    AssistantDirectory,
    AssistantDirectoryUnavailable,
)
from src.application.use_cases.register_agent import RegisterAgent
from src.domain.agent import Agent
from src.infrastructure.db.session import get_session
from src.infrastructure.repositories.governance_query import SqlAlchemyGovernanceQuery
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

router = APIRouter(tags=["agents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_assistant_directory() -> AssistantDirectory:
    """Production wiring for the outbound Vapi verification gate.

    Always constructs the real adapter — there is no code path that skips
    verification. Tests override this dependency with a fake.
    """
    return VapiAssistantDirectory()


DirectoryDep = Annotated[AssistantDirectory, Depends(get_assistant_directory)]


@router.post("/agents", status_code=200, summary="Register an agent")
async def register_agent(
    body: RegisterAgentIn, db: SessionDep, directory: DirectoryDep
) -> AgentOut:
    repository = SqlAlchemyGovernanceRepository(db)
    try:
        agent = await RegisterAgent(repository, directory).execute(body.to_command())
    except AssistantNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Vapi assistant not found") from exc
    except AssistantDirectoryUnavailable as exc:
        raise HTTPException(status_code=502, detail="Cannot verify assistant with Vapi") from exc
    await db.commit()
    return _to_agent_out(agent)


@router.get("/agents", summary="List agents")
async def list_agents(db: SessionDep) -> list[AgentOut]:
    agents = await SqlAlchemyGovernanceQuery(db).list_agents()
    return [_to_agent_out(agent) for agent in agents]


def _to_agent_out(agent: Agent) -> AgentOut:
    return AgentOut(
        agent_id=agent.agent_id,
        name=agent.name,
        objective=agent.objective,
        description=agent.description,
        vapi_assistant_id=agent.vapi_assistant_id,
        status=agent.status.value,
    )
