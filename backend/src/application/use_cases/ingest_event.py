from src.application.commands import IngestEventCommand
from src.application.ports.governance_repository import GovernanceRepository
from src.domain.agent import Agent
from src.domain.enums import AgentStatus, EventType, SessionStatus
from src.domain.event import Event
from src.domain.session import Session


class IngestEvent:
    """Resolve/create the Session for a call and record a canonical event.

    Idempotent on session boundaries: duplicate `session.started` and any event
    after the session closed are ignored (Vapi emits several near the edges).
    Unknown agents are auto-provisioned so no session is ever lost.
    """

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(self, command: IngestEventCommand) -> Event | None:
        agent = await self._repo.get_agent_by_assistant_id(command.assistant_id)
        if agent is None:
            agent = Agent(
                name=f"Unregistered {command.assistant_id}",
                objective="(unregistered)",
                vapi_assistant_id=command.assistant_id,
                status=AgentStatus.UNREGISTERED,
            )
            await self._repo.add_agent(agent)

        session = await self._repo.get_session_for_update(command.call_id)
        if session is None:
            session = Session.open(command.call_id, agent.agent_id, command.timestamp)
            if not await self._repo.create_session(session):
                session = await self._repo.get_session_for_update(command.call_id)
                if session is None:
                    return None
                if command.event_type is EventType.SESSION_STARTED:
                    return None
                if session.status is not SessionStatus.ACTIVE:
                    return None
        elif command.event_type is EventType.SESSION_STARTED:
            return None  # idempotent: duplicate session start
        elif session.status is not SessionStatus.ACTIVE:
            return None  # idempotent: session already closed

        event = session.record(
            command.event_type, command.source, command.timestamp, command.payload
        )
        await self._repo.save_session(session)
        return event
