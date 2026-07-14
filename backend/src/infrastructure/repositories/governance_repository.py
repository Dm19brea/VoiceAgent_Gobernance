from dataclasses import replace
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent import Agent
from src.domain.enums import (
    AgentStatus,
    Dimension,
    EvaluationResult,
    EventType,
    EvidenceType,
    SessionStatus,
    Source,
)
from src.domain.evaluation_report import EvaluationReport
from src.domain.event import Event
from src.domain.evidence import Evidence
from src.domain.scoring.flags import BlockingFlag
from src.domain.scoring.metric import Metric
from src.domain.session import Session
from src.infrastructure.db.models import (
    AgentModel,
    EvaluationReportModel,
    EventModel,
    EvidenceModel,
    SessionModel,
)


class SqlAlchemyGovernanceRepository:
    """SQLAlchemy implementation of the GovernanceRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_agent_by_assistant_id(self, assistant_id: str) -> Agent | None:
        row = await self._session.scalar(
            select(AgentModel).where(AgentModel.vapi_assistant_id == assistant_id)
        )
        return _to_agent(row) if row is not None else None

    async def add_agent(self, agent: Agent) -> None:
        self._session.add(_to_agent_model(agent))
        await self._session.flush()

    async def upsert_agent(self, agent: Agent) -> Agent:
        """Create or promote an agent by ``vapi_assistant_id``, atomically.

        ``agent_id`` is deliberately excluded from ``set_`` so a conflicting
        update preserves the pre-existing row's primary key. ``description``
        is only included in ``set_`` when explicitly provided (not ``None``),
        so an omitted description preserves the prior value on update.
        """
        set_: dict[str, Any] = {
            "name": agent.name,
            "objective": agent.objective,
            "status": agent.status.value,
        }
        if agent.description is not None:
            set_["description"] = agent.description
        stmt = (
            pg_insert(AgentModel)
            .values(
                agent_id=agent.agent_id,
                name=agent.name,
                objective=agent.objective,
                vapi_assistant_id=agent.vapi_assistant_id,
                description=agent.description if agent.description is not None else "",
                status=agent.status.value,
            )
            .on_conflict_do_update(index_elements=["vapi_assistant_id"], set_=set_)
            .returning(AgentModel)
        )
        row = (await self._session.execute(stmt)).scalar_one()
        await self._session.flush()
        return _to_agent(row)

    async def get_session(self, session_id: str) -> Session | None:
        return await self._load_session(session_id, for_update=False)

    async def get_session_for_update(self, session_id: str) -> Session | None:
        """Load a session under a row lock before assigning another sequence."""
        return await self._load_session(session_id, for_update=True)

    async def create_session(self, session: Session) -> bool:
        """Create a session once, letting concurrent starters converge safely."""
        stmt = (
            pg_insert(SessionModel)
            .values(
                session_id=session.session_id,
                agent_id=session.agent_id,
                status=session.status.value,
                started_at=session.started_at,
                ended_at=session.ended_at,
            )
            .on_conflict_do_nothing(index_elements=["session_id"])
            .returning(SessionModel.session_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _load_session(self, session_id: str, *, for_update: bool) -> Session | None:
        statement = select(SessionModel).where(SessionModel.session_id == session_id)
        if for_update:
            statement = statement.with_for_update()
        row = await self._session.scalar(statement)
        if row is None:
            return None
        event_rows = (
            await self._session.scalars(
                select(EventModel)
                .where(EventModel.session_id == session_id)
                .order_by(EventModel.sequence_number)
            )
        ).all()
        return _to_session(row, list(event_rows))

    async def save_session(self, session: Session) -> None:
        await self._session.merge(_to_session_model(session))
        for event in session.events:
            await self.append_event(event)

    async def append_event(self, event: Event) -> bool:
        """Insert one canonical event idempotently by deterministic event identity."""
        stmt = (
            pg_insert(EventModel)
            .values(**_event_values(event))
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(EventModel.event_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def append_marker_event(self, event: Event) -> None:
        """Idempotently append a post-terminal marker event.

        Never touches the ``sessions`` row (no ``save_session``/``merge``): the
        session is already closed, so only the ``events`` insert matters. The
        partial unique index on (session_id, event_type) makes a retried
        append a no-op via ``ON CONFLICT ... DO NOTHING``.
        """
        await self._session.scalar(
            select(SessionModel)
            .where(SessionModel.session_id == event.session_id)
            .with_for_update()
        )
        max_sequence = await self._session.scalar(
            select(func.coalesce(func.max(EventModel.sequence_number), 0)).where(
                EventModel.session_id == event.session_id
            )
        )
        next_sequence = (max_sequence or 0) + 1
        serialized_event = replace(event, sequence_number=next_sequence)
        stmt = (
            pg_insert(EventModel)
            .values(**_event_values(serialized_event))
            .on_conflict_do_nothing(
                index_elements=["session_id", "event_type"],
                index_where=EventModel.event_type.in_(
                    [EventType.SESSION_EVALUATION_TRIGGERED.value, EventType.SESSION_FAILED.value]
                ),
            )
        )
        await self._session.execute(stmt)

    async def add_evidences(self, evidences: list[Evidence]) -> None:
        # Evidences are rebuilt per session (the webhook can fire more than once),
        # so replace any existing ones for the affected sessions to stay idempotent.
        session_ids = {evidence.session_id for evidence in evidences}
        if session_ids:
            await self._session.execute(
                delete(EvidenceModel).where(EvidenceModel.session_id.in_(session_ids))
            )
        for evidence in evidences:
            self._session.add(_to_evidence_model(evidence))
        await self._session.flush()

    async def get_evidences_by_session(self, session_id: str) -> list[Evidence]:
        rows = (
            await self._session.scalars(
                select(EvidenceModel).where(EvidenceModel.session_id == session_id)
            )
        ).all()
        return [_to_evidence(row) for row in rows]

    async def add_report(self, report: EvaluationReport) -> None:
        # One report per session: replace any existing one so scoring stays idempotent.
        await self._session.execute(
            delete(EvaluationReportModel).where(
                EvaluationReportModel.session_id == report.session_id
            )
        )
        self._session.add(_to_report_model(report))
        await self._session.flush()

    async def get_report_by_session(self, session_id: str) -> EvaluationReport | None:
        row = await self._session.scalar(
            select(EvaluationReportModel).where(EvaluationReportModel.session_id == session_id)
        )
        return _to_report(row) if row is not None else None


def _to_agent(row: AgentModel) -> Agent:
    return Agent(
        name=row.name,
        objective=row.objective,
        vapi_assistant_id=row.vapi_assistant_id,
        description=row.description,
        status=AgentStatus(row.status),
        agent_id=row.agent_id,
    )


def _to_agent_model(agent: Agent) -> AgentModel:
    return AgentModel(
        agent_id=agent.agent_id,
        name=agent.name,
        objective=agent.objective,
        vapi_assistant_id=agent.vapi_assistant_id,
        description=agent.description,
        status=agent.status.value,
    )


def _to_session(row: SessionModel, event_rows: list[EventModel]) -> Session:
    return Session(
        session_id=row.session_id,
        agent_id=row.agent_id,
        started_at=row.started_at,
        status=SessionStatus(row.status),
        ended_at=row.ended_at,
        events=[_to_event(event) for event in event_rows],
    )


def _to_session_model(session: Session) -> SessionModel:
    return SessionModel(
        session_id=session.session_id,
        agent_id=session.agent_id,
        status=session.status.value,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


def _to_event(row: EventModel) -> Event:
    return Event(
        session_id=row.session_id,
        event_type=EventType(row.event_type),
        source=Source(row.source),
        sequence_number=row.sequence_number,
        timestamp=row.timestamp,
        payload=row.payload,
        event_id=row.event_id,
    )


def _event_values(event: Event) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "session_id": event.session_id,
        "event_type": event.event_type.value,
        "source": event.source.value,
        "sequence_number": event.sequence_number,
        "timestamp": event.timestamp,
        "payload": event.payload,
    }


def _to_evidence_model(evidence: Evidence) -> EvidenceModel:
    return EvidenceModel(
        evidence_id=evidence.evidence_id,
        session_id=evidence.session_id,
        evidence_type=evidence.evidence_type.value,
        criterion=evidence.criterion,
        conclusion=evidence.conclusion,
        value=evidence.value,
        dimension=evidence.dimension.value,
        source_events=[str(event_id) for event_id in evidence.source_events],
        generated_at=evidence.generated_at,
    )


def _to_evidence(row: EvidenceModel) -> Evidence:
    return Evidence(
        session_id=row.session_id,
        evidence_type=EvidenceType(row.evidence_type),
        criterion=row.criterion,
        conclusion=row.conclusion,
        dimension=Dimension(row.dimension),
        source_events=[UUID(event_id) for event_id in row.source_events],
        value=row.value,
        evidence_id=row.evidence_id,
        generated_at=row.generated_at,
    )


def _to_report_model(report: EvaluationReport) -> EvaluationReportModel:
    return EvaluationReportModel(
        report_id=report.report_id,
        session_id=report.session_id,
        score_global=report.score_global,
        result=report.result.value,
        score_conversational=report.score_conversational,
        score_operational=report.score_operational,
        score_technical=report.score_technical,
        score_risk=report.score_risk,
        blocking_flags=[
            {"code": flag.code, "reason": flag.reason} for flag in report.blocking_flags
        ],
        metrics=[_metric_to_dict(metric) for metric in report.metrics],
        generated_at=report.generated_at,
    )


def _to_report(row: EvaluationReportModel) -> EvaluationReport:
    return EvaluationReport(
        session_id=row.session_id,
        score_global=row.score_global,
        result=EvaluationResult(row.result),
        score_conversational=row.score_conversational,
        score_operational=row.score_operational,
        score_technical=row.score_technical,
        score_risk=row.score_risk,
        blocking_flags=[
            BlockingFlag(code=flag["code"], reason=flag["reason"]) for flag in row.blocking_flags
        ],
        metrics=[_dict_to_metric(data) for data in row.metrics],
        report_id=row.report_id,
        generated_at=row.generated_at,
    )


def _metric_to_dict(metric: Metric) -> dict[str, Any]:
    return {
        "code": metric.code,
        "dimension": metric.dimension.value,
        "raw_value": metric.raw_value,
        "normalized_score": metric.normalized_score,
        "weight": metric.weight,
        "unit": metric.unit,
    }


def _dict_to_metric(data: dict[str, Any]) -> Metric:
    return Metric(
        code=data["code"],
        dimension=Dimension(data["dimension"]),
        raw_value=data["raw_value"],
        normalized_score=data["normalized_score"],
        weight=data["weight"],
        unit=data["unit"],
    )
