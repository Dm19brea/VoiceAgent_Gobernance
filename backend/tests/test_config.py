import pytest

from src.infrastructure.config import Settings, _dotenv_file


def test_pytest_disables_dotenv_file() -> None:
    assert Settings.model_config["env_file"] is None


def test_application_defaults_to_dotenv_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOVERNANCE_DISABLE_DOTENV", raising=False)

    assert _dotenv_file() == ".env"
