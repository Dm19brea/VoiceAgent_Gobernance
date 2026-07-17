import pytest

from src.domain.agent import Agent
from src.domain.enums import AgentStatus


def test_agent_valid() -> None:
    agent = Agent(name="Citas", objective="Confirmar citas", vapi_assistant_id="asst_1")

    assert agent.status is AgentStatus.ACTIVE
    assert agent.vapi_assistant_id == "asst_1"
    assert agent.agent_id is not None


def test_agent_empty_name_rejected() -> None:
    with pytest.raises(ValueError):
        Agent(name="", objective="Confirmar citas", vapi_assistant_id="asst_1")


def test_agent_empty_objective_rejected() -> None:
    with pytest.raises(ValueError):
        Agent(name="Citas", objective="", vapi_assistant_id="asst_1")


def test_agent_webhook_activated_defaults_false() -> None:
    agent = Agent(name="Citas", objective="Confirmar citas", vapi_assistant_id="asst_1")

    assert agent.webhook_activated is False


def test_agent_webhook_activated_explicit_true_honored() -> None:
    agent = Agent(
        name="Citas",
        objective="Confirmar citas",
        vapi_assistant_id="asst_1",
        webhook_activated=True,
    )

    assert agent.webhook_activated is True
