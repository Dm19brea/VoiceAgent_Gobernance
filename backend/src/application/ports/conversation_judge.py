from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """Structured outcome of an LLM-judge pass over a full call transcript."""

    topic_change_count: int
    topics: list[str]
    topic_reason: str | None
    goal_achieved: bool
    goal_reason: str


class ConversationJudge(Protocol):
    """Outbound port for the post-terminal conversation judge.

    Implementations own their own retry/backoff policy and MUST never raise:
    any unrecoverable failure (timeout, rate limit, malformed output) after
    exhausting the attempt budget resolves to ``None``.
    """

    async def evaluate(self, transcript: str) -> JudgeVerdict | None: ...
