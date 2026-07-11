"""OpenRouter-backed adapter for the post-terminal ``ConversationJudge`` port.

Owns all HTTP concerns (endpoint, retry/backoff, per-attempt timeout, strict
JSON parsing). The application layer never imports ``httpx`` directly; it
depends only on the ``ConversationJudge`` Protocol.
"""

import asyncio
import json
import logging
from typing import Any

import httpx

from src.application.ports.conversation_judge import JudgeVerdict
from src.infrastructure.config import Settings
from src.infrastructure.config import settings as default_settings

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (0.5, 1.0, 2.0)
_CHAT_COMPLETIONS_PATH = "/chat/completions"
_MODEL = "openrouter/free"

_SYSTEM_PROMPT = (
    "You are a governance judge reviewing a completed voice-agent call transcript. "
    "Reply with STRICT JSON only, no prose, matching exactly this shape: "
    '{"topic_change":{"count":<int>,"topics":[<string>,...],"reason":<string>},'
    '"goal":{"verdict":"achieved"|"failed","reason":<string>}}. '
    "count is the number of distinct topic shifts in the call (0 if the call stayed on "
    'one topic). verdict is "achieved" if the caller\'s stated goal was resolved or the '
    'call was purely informational, "failed" otherwise.'
)


class OpenRouterConversationJudge:
    """Implements ``ConversationJudge`` against the OpenRouter chat completions API."""

    def __init__(
        self,
        config: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = config or default_settings
        self._client = client

    async def evaluate(self, transcript: str) -> JudgeVerdict | None:
        api_key = self._settings.openrouter_api_key
        if not api_key:
            logger.warning("Conversation judge skipped: OPENROUTER_API_KEY is not configured")
            return None

        for attempt in range(_MAX_ATTEMPTS):
            try:
                content = await self._call(transcript, api_key)
                verdict = _parse_verdict(content)
                if verdict is not None:
                    return verdict
                logger.warning(
                    "Conversation judge attempt %s/%s returned malformed output",
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
            except Exception:
                logger.warning(
                    "Conversation judge attempt %s/%s failed",
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    exc_info=True,
                )

            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])

        logger.error("Conversation judge exhausted %s attempts; yielding no signals", _MAX_ATTEMPTS)
        return None

    async def _call(self, transcript: str, api_key: str) -> str:
        client = self._client
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(base_url=self._settings.openrouter_base_url)
        try:
            response = await client.post(
                _CHAT_COMPLETIONS_PATH,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": _MODEL,
                    "reasoning": {"enabled": True},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": transcript},
                    ],
                },
                timeout=self._settings.openrouter_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"])
        finally:
            if owns_client:
                await client.aclose()


def _parse_verdict(raw: str) -> JudgeVerdict | None:
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    topic_change = data.get("topic_change")
    goal = data.get("goal")
    if not isinstance(topic_change, dict) or not isinstance(goal, dict):
        return None

    count = topic_change.get("count")
    topics = topic_change.get("topics")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return None
    if not isinstance(topics, list) or not all(isinstance(topic, str) for topic in topics):
        return None

    topic_reason = topic_change.get("reason")
    if topic_reason is not None and not isinstance(topic_reason, str):
        return None

    verdict_raw = goal.get("verdict")
    goal_reason = goal.get("reason")
    if verdict_raw not in ("achieved", "failed"):
        return None
    if not isinstance(goal_reason, str) or not goal_reason.strip():
        return None

    return JudgeVerdict(
        topic_change_count=count,
        topics=topics,
        topic_reason=topic_reason,
        goal_achieved=verdict_raw == "achieved",
        goal_reason=goal_reason,
    )
