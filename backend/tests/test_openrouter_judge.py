import json

import httpx
import pytest

from src.adapters.llm.openrouter_judge import OpenRouterConversationJudge
from src.application.ports.conversation_judge import JudgeVerdict
from src.infrastructure.config import Settings


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "openrouter_api_key": "test-key",
        "openrouter_base_url": "https://openrouter.test/api/v1",
        "openrouter_timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _reply_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


def _valid_content(
    *, count: int = 2, topics: list[str] | None = None, verdict: str = "achieved"
) -> str:
    return json.dumps(
        {
            "topic_change": {
                "count": count,
                "topics": topics if topics is not None else ["billing", "cancellation"],
                "reason": "shifted twice",
            },
            "goal": {"verdict": verdict, "reason": "caller's issue was resolved"},
        }
    )


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.fixture(autouse=True)
def _skip_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.adapters.llm.openrouter_judge.asyncio.sleep", _no_sleep)


async def test_evaluate_returns_verdict_for_valid_strict_json_reply() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _reply_response(_valid_content())

    client = httpx.AsyncClient(
        base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(handler)
    )
    judge = OpenRouterConversationJudge(config=_settings(), client=client)

    verdict = await judge.evaluate("caller: hi\nagent: hello")

    assert calls == 1
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.topic_change_count == 2
    assert verdict.topics == ["billing", "cancellation"]
    assert verdict.goal_achieved is True
    assert verdict.goal_reason == "caller's issue was resolved"
    await client.aclose()


async def test_evaluate_treats_malformed_reply_as_failed_attempt_and_exhausts_retries() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _reply_response("not json at all")

    client = httpx.AsyncClient(
        base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(handler)
    )
    judge = OpenRouterConversationJudge(config=_settings(), client=client)

    verdict = await judge.evaluate("transcript")

    assert verdict is None
    assert calls == 3
    await client.aclose()


async def test_evaluate_succeeds_on_second_attempt_after_first_times_out() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.TimeoutException("timed out", request=request)
        return _reply_response(_valid_content(count=1, topics=["billing"], verdict="failed"))

    client = httpx.AsyncClient(
        base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(handler)
    )
    judge = OpenRouterConversationJudge(config=_settings(), client=client)

    verdict = await judge.evaluate("transcript")

    assert calls == 2
    assert verdict is not None
    assert verdict.topic_change_count == 1
    assert verdict.goal_achieved is False
    await client.aclose()


async def test_evaluate_exhausts_all_three_attempts_with_mixed_failures() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.TimeoutException("timed out", request=request)
        if calls == 2:
            return httpx.Response(429, json={"error": "rate limited"})
        return _reply_response("{not valid json")

    client = httpx.AsyncClient(
        base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(handler)
    )
    judge = OpenRouterConversationJudge(config=_settings(), client=client)

    verdict = await judge.evaluate("transcript")

    assert verdict is None
    assert calls == 3
    await client.aclose()


async def test_evaluate_returns_none_without_calling_api_when_key_missing() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _reply_response(_valid_content())

    client = httpx.AsyncClient(
        base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(handler)
    )
    judge = OpenRouterConversationJudge(config=_settings(openrouter_api_key=""), client=client)

    verdict = await judge.evaluate("transcript")

    assert verdict is None
    assert calls == 0
    await client.aclose()
