"""Agent registration and listing endpoints (PR1 R1-R9, PR2 R10-R11)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.agent_schemas import AgentOut, RegisterAgentIn
from src.application.use_cases.register_agent import RegisterAgent
from src.domain.agent import Agent
from src.infrastructure.db.session import get_session
from src.infrastructure.repositories.governance_query import SqlAlchemyGovernanceQuery
from src.infrastructure.repositories.governance_repository import SqlAlchemyGovernanceRepository

router = APIRouter(tags=["agents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/agents", status_code=200, summary="Register an agent")
async def register_agent(body: RegisterAgentIn, db: SessionDep) -> AgentOut:
    repository = SqlAlchemyGovernanceRepository(db)
    agent = await RegisterAgent(repository).execute(body.to_command())
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
