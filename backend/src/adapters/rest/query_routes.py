"""Query endpoints: read side of the API (doc 4.4 §4.4.3, Grupo 3)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.query_schemas import SessionOut, SessionSummaryOut
from src.application.ports.query import SessionSummary
from src.domain.enums import EvaluationResult, EventType
from src.domain.session import Session
from src.infrastructure.db.session import get_session
from src.infrastructure.repositories.governance_query import SqlAlchemyGovernanceQuery

router = APIRouter(tags=["query"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/sessions/{session_id}", response_model=SessionOut, summary="Get session state")
async def get_session_detail(session_id: str, db: SessionDep) -> SessionOut:
    session = await SqlAlchemyGovernanceQuery(db).get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_session_out(session)


@router.get(
    "/agents/{agent_id}/sessions",
    response_model=list[SessionSummaryOut],
    summary="List an agent's sessions",
)
async def list_agent_sessions(
    agent_id: UUID,
    db: SessionDep,
    result: EvaluationResult | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SessionSummaryOut]:
    summaries = await SqlAlchemyGovernanceQuery(db).list_agent_sessions(
        agent_id, result=result, limit=limit, offset=offset
    )
    return [_to_summary_out(summary) for summary in summaries]


def _to_session_out(session: Session) -> SessionOut:
    agent_turns = sum(
        1 for event in session.events if event.event_type is EventType.CONVERSATION_AGENT_RESPONSE
    )
    user_turns = sum(
        1 for event in session.events if event.event_type is EventType.CONVERSATION_USER_INPUT
    )
    return SessionOut(
        session_id=session.session_id,
        agent_id=session.agent_id,
        status=session.status.value,
        started_at=session.started_at,
        ended_at=session.ended_at,
        total_turns=agent_turns + user_turns,
        agent_turns=agent_turns,
        user_turns=user_turns,
    )


def _to_summary_out(summary: SessionSummary) -> SessionSummaryOut:
    return SessionSummaryOut(
        session_id=summary.session_id,
        status=summary.status.value,
        started_at=summary.started_at,
        ended_at=summary.ended_at,
        result=summary.result.value if summary.result is not None else "pending",
        score_global=summary.score_global,
    )
