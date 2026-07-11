"""Manual smoke check for the real OpenRouter conversation judge.

This exercises the ACTUAL production adapter (``OpenRouterConversationJudge``)
against the live OpenRouter API, so it validates the real request payload
(model string, ``reasoning`` block, auth header) that the unit tests can only
fake with ``httpx.MockTransport``.

Run it from the ``backend/`` directory so the ``.env`` file and the ``src``
package resolve:

    uv run python scripts/check_openrouter_judge.py

It reads ``OPENROUTER_API_KEY`` from ``backend/.env`` (or the environment).
Nothing is committed and no key is printed.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Make ``src`` importable regardless of how the script is launched.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.adapters.llm.openrouter_judge import OpenRouterConversationJudge  # noqa: E402
from src.infrastructure.config import settings  # noqa: E402

# Surface each attempt (rate limits, malformed output) instead of silently
# collapsing to ``None`` after the retry budget is exhausted.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# A short, realistic transcript with one clear topic shift and a resolved goal,
# so a healthy model should return count>=1 and verdict="achieved".
TRANSCRIPT = """\
[assistant] Hello, this is the appointments line. How can I help you today?
[user] Hi, I need to move my dental appointment from Tuesday to Thursday.
[assistant] Sure. I've rescheduled your appointment to Thursday at 10:00. Anything else?
[user] Yes, actually — do you also handle billing questions? I think I was overcharged.
[assistant] I can help with that. I see a duplicate charge and I've issued a refund of 20 euros.
[user] Perfect, thank you.
[assistant] You're welcome. Have a great day.
"""


async def main() -> int:
    if not settings.openrouter_api_key:
        print(
            "OPENROUTER_API_KEY is not set.\n"
            "Add it to backend/.env (from the backend/ directory) with:\n"
            "  printf 'OPENROUTER_API_KEY=%s\\n' 'YOUR_KEY' >> .env\n"
            "then re-run this script."
        )
        return 1

    print(f"Base URL : {settings.openrouter_base_url}")
    print(f"Timeout  : {settings.openrouter_timeout_seconds}s")
    print("Calling the real OpenRouter API (free model auto-select)...\n")

    judge = OpenRouterConversationJudge()
    verdict = await judge.evaluate(TRANSCRIPT)

    print()
    if verdict is None:
        print(
            "Result: None — the judge exhausted its retries (rate limit, timeout, "
            "or malformed output). See the WARNING/ERROR logs above for the cause.\n"
            "Note: free models are frequently rate-limited; this is exactly the "
            "failure the pipeline isolates so it never blocks content derivation."
        )
        return 2

    print("Result: verdict parsed successfully from the LIVE API")
    print(f"  topic_change_count : {verdict.topic_change_count}")
    print(f"  topics             : {verdict.topics}")
    print(f"  topic_reason       : {verdict.topic_reason}")
    print(f"  goal_achieved      : {verdict.goal_achieved}")
    print(f"  goal_reason        : {verdict.goal_reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
