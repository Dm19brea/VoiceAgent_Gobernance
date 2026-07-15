"""PR1 R1 — VapiAssistantDirectory adapter (S2, S3): fail-closed verification."""

import httpx
import pytest

from src.adapters.vapi.assistant_directory import VapiAssistantDirectory
from src.application.ports.assistant_directory import AssistantDirectoryUnavailable
from src.infrastructure.config import Settings


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "vapi_api_key": "test-vapi-key",
        "vapi_base_url": "https://vapi.test",
        "vapi_timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


async def test_exists_returns_true_on_200() -> None:
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json={"id": "asst-1"})

    client = httpx.AsyncClient(base_url="https://vapi.test", transport=httpx.MockTransport(handler))
    directory = VapiAssistantDirectory(config=_settings(), client=client)

    result = await directory.exists("asst-1")

    assert result is True
    assert seen_headers["authorization"] == "test-vapi-key"
    await client.aclose()


async def test_exists_returns_false_on_404() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    client = httpx.AsyncClient(base_url="https://vapi.test", transport=httpx.MockTransport(handler))
    directory = VapiAssistantDirectory(config=_settings(), client=client)

    result = await directory.exists("missing-asst")

    assert result is False
    await client.aclose()


async def test_exists_raises_unavailable_on_server_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    client = httpx.AsyncClient(base_url="https://vapi.test", transport=httpx.MockTransport(handler))
    directory = VapiAssistantDirectory(config=_settings(), client=client)

    with pytest.raises(AssistantDirectoryUnavailable):
        await directory.exists("asst-1")

    await client.aclose()


async def test_exists_raises_unavailable_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = httpx.AsyncClient(base_url="https://vapi.test", transport=httpx.MockTransport(handler))
    directory = VapiAssistantDirectory(config=_settings(), client=client)

    with pytest.raises(AssistantDirectoryUnavailable):
        await directory.exists("asst-1")

    await client.aclose()


async def test_exists_raises_unavailable_on_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.AsyncClient(base_url="https://vapi.test", transport=httpx.MockTransport(handler))
    directory = VapiAssistantDirectory(config=_settings(), client=client)

    with pytest.raises(AssistantDirectoryUnavailable):
        await directory.exists("asst-1")

    await client.aclose()
