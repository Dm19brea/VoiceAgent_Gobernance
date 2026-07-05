"""Query endpoints: read side of the API (doc 4.4 §4.4.3, Grupo 3)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.rest.query_schemas import (
    BlockingFlagOut,
    EventOut,
    EvidenceOut,
    ReportOut,
    ScoresOut,
    SessionOut,
    SessionSummaryOut,
)
from src.application.ports.query import SessionSummary
from src.domain.enums import EvaluationResult, EventType, Source
from src.domain.evaluation_report import EvaluationReport
from src.domain.event import Event
from src.domain.evidence import Evidence
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


@router.get(
    "/sessions/{session_id}/report",
    response_model=ReportOut,
    summary="Get a session's evaluation report",
)
async def get_session_report(session_id: str, db: SessionDep) -> ReportOut:
    report = await SqlAlchemyGovernanceQuery(db).get_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return _to_report_out(report)


@router.get(
    "/sessions/{session_id}/evidences",
    response_model=list[EvidenceOut],
    summary="Get a session's evidences",
)
async def get_session_evidences(session_id: str, db: SessionDep) -> list[EvidenceOut]:
    evidences = await SqlAlchemyGovernanceQuery(db).get_evidences(session_id)
    return [_to_evidence_out(evidence) for evidence in evidences]


@router.get(
    "/sessions/{session_id}/events",
    response_model=list[EventOut],
    summary="Get a session's event trace",
)
async def get_session_events(
    session_id: str,
    db: SessionDep,
    event_type: EventType | None = None,
    source: Source | None = None,
) -> list[EventOut]:
    events = await SqlAlchemyGovernanceQuery(db).get_events(
        session_id, event_type=event_type, source=source
    )
    return [_to_event_out(event) for event in events]


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


def _to_report_out(report: EvaluationReport) -> ReportOut:
    return ReportOut(
        report_id=report.report_id,
        session_id=report.session_id,
        score_global=report.score_global,
        scores=ScoresOut(
            conversational=report.score_conversational,
            operational=report.score_operational,
            technical=report.score_technical,
            risk=report.score_risk,
        ),
        result=report.result.value,
        blocking_flags=[
            BlockingFlagOut(code=flag.code, reason=flag.reason) for flag in report.blocking_flags
        ],
        generated_at=report.generated_at,
    )


def _to_evidence_out(evidence: Evidence) -> EvidenceOut:
    return EvidenceOut(
        evidence_id=evidence.evidence_id,
        session_id=evidence.session_id,
        evidence_type=evidence.evidence_type.value,
        criterion=evidence.criterion,
        conclusion=evidence.conclusion,
        dimension=evidence.dimension.value,
        value=evidence.value,
        generated_at=evidence.generated_at,
    )


def _to_event_out(event: Event) -> EventOut:
    return EventOut(
        event_id=event.event_id,
        session_id=event.session_id,
        event_type=event.event_type.value,
        source=event.source.value,
        sequence_number=event.sequence_number,
        timestamp=event.timestamp,
        payload=event.payload,
    )
