# Design: LLM-judge post-terminal conversation signals

## Technical Approach

Reuse the proven post-terminal idempotent pipeline. After `_record_conversation_content`
commits (tasks.py:75), add a best-effort `_record_conversation_signals` step in
`build_session_evidences_async`. It builds a structured transcript string from the SAME
`artifact.messagesOpenAIFormatted` used by `derive_conversation_content`, calls an
OpenRouter judge through a new hexagonal outbound port, parses the structured reply into
`ConversationSignalCommand`s, and appends them via a `RecordConversationSignals` use case
that mirrors `RecordConversationContent` UUID5 idempotency. The three `EventType` values
already exist — no taxonomy change. The judge is fully isolated: any failure logs and
returns, leaving content events and session lifecycle untouched.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Judge boundary | New `ConversationJudge` Protocol port in `application/ports/conversation_judge.py`; `OpenRouterConversationJudge` adapter in `adapters/llm/openrouter_judge.py` | Calling `requests`/httpx from the use case or tasks | Keeps hexagonal boundaries; use case depends on the port, not HTTP. Fakeable for Strict TDD. |
| Orchestration site | Isolated `_record_conversation_signals` in tasks.py after content, own engine/NullPool, try/except+log | Inline in `_record_conversation_content`; separate Celery task | Same failure-isolation shape as `_record_evaluation_observations`; signals are best-effort enrichment, never on the critical path. |
| Retry policy | Adapter owns bounded retry: MAX 3 attempts, exponential backoff (e.g. 0.5s/1s/2s), per-attempt timeout; malformed/unparseable reply counts as a failed attempt | Celery `autoretry`; unbounded retry | Retry is a transport concern local to the adapter; Celery retry would re-run the whole evidence task. Exhaustion → return `None` → no events. |
| Model selection | `"model": "openrouter/auto"`-style free auto-select, `reasoning.enabled=true`, no pinned id; key from `OPENROUTER_API_KEY` env | Pinned free model id | Free models rotate/deprecate; auto-select survives churn. Config via `Settings`. |
| Output contract | Prompt demands strict JSON: `{"topic_change":{"count":int,"topics":[str],"reason":str?},"goal":{"verdict":"achieved"|"failed","reason":str}}`; parser validates shape/types, malformed = failed attempt | Free-text + regex scraping | Deterministic parse; failure isolation requires a hard schema. Info-only call → `goal.verdict="achieved"`. |
| Signal identity | `RecordConversationSignals` + `canonical_signal_event_id`, `schema_version="conversation-signal/v1"`, UUID5(NAMESPACE_URL) over `{event_type, identity, schema_version, session_id}` | Timestamps/raw ids in fingerprint | Redelivery/reprocess recomputes same id → `existing` short-circuit + ON CONFLICT no-op. `identity` = topic: `{count}`; goal: `{verdict}` (stable outcome fields, not `reason`). |
| Domain append | Add `_SIGNAL_EVENTS = {TOPIC_CHANGE, GOAL_ACHIEVED, GOAL_FAILED}` + `append_conversation_signal` (rejects ACTIVE, wrong type; never mutates status/ended_at) | Reuse `append_conversation_content` | Same invariant as content/observation appends; keeps signal semantics separate. |

## Data Flow

    build_session_evidences_async:
      RecordEvaluationTriggered (own commit)
      build_evidences → report (commit)
      _record_evaluation_observations (isolated)
      _record_conversation_content (isolated)
      _record_conversation_signals (isolated)          ← NEW, best-effort
          │ build transcript string ← artifact.messagesOpenAIFormatted (terminal payload)
          │ ConversationJudge.evaluate(transcript) → OpenRouter (≤3 attempts, backoff)
          │   └─ parse JSON → JudgeVerdict | None(failure ⇒ return, no events)
          └─→ RecordConversationSignals → append_conversation_signal → append_event (UUID5 dedup)

## File Changes

| File | Action | Description |
|---|---|---|
| `application/ports/conversation_judge.py` | Create | `ConversationJudge` Protocol + `JudgeVerdict` DTO |
| `adapters/llm/openrouter_judge.py` | Create | OpenRouter adapter: env key, timeout, 3-retry+backoff, JSON parse/validate |
| `adapters/rest/vapi_mapping.py` | Modify | `build_judge_transcript(report_message)` string builder; `verdict_to_signal_commands(verdict, session_id, ts)` mapper |
| `application/commands.py` | Modify | `ConversationSignalCommand` (event_type, source, timestamp, identity_fields, payload) |
| `application/use_cases/record_conversation_signals.py` | Create | `canonical_signal_event_id` + `RecordConversationSignals` |
| `domain/session.py` | Modify | `_SIGNAL_EVENTS` + `append_conversation_signal` |
| `infrastructure/config.py` | Modify | `openrouter_api_key`, `openrouter_base_url`, `openrouter_timeout_seconds` |
| `infrastructure/celery/tasks.py` | Modify | `_record_conversation_signals` isolated step after content |
| `backend/tests/...` | Create/Modify | Fake-judge unit + integration coverage |

## Interfaces / Contracts

```python
@runtime_checkable
class ConversationJudge(Protocol):
    def evaluate(self, transcript: str) -> JudgeVerdict | None: ...  # None = give up

@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    topic_change_count: int
    topics: list[str]
    topic_reason: str | None
    goal_achieved: bool         # False ⇒ GOAL_FAILED
    goal_reason: str

@dataclass(frozen=True, slots=True)
class ConversationSignalCommand:
    session_id: str
    event_type: EventType
    source: Source              # Source.PLATFORM (inferred)
    timestamp: datetime         # ended_at
    identity_fields: dict[str, Any]  # topic:{count}; goal:{verdict}
    payload: dict[str, Any]     # topic:{count,topics,reason?}; goal:{reason}
```

Payloads persisted: topic_change → `{count, topics[], reason?, identity}`;
goal verdict → `{reason, identity}`.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | `build_judge_transcript` shape; `verdict_to_signal_commands` (achieved/failed, topic count/topics) | pure fns over fixture report |
| Unit | `canonical_signal_event_id` stability (same verdict → same id; count/verdict-only identity) | pure fn |
| Unit | `append_conversation_signal` rejects ACTIVE/wrong type; sequence_number | domain tests |
| Unit | adapter parse: valid JSON→verdict; malformed→None; retry exhaustion→None | fake HTTP transport |
| Integration | `_record_conversation_signals` writes ≤1 topic + 1 goal; re-run/redelivery = 0 dups | inject FakeConversationJudge, DB round-trip |
| Integration | judge raises/returns None → content events intact, task succeeds | failing fake judge |

## Migration / Rollout

No migration. Additive, isolated events. Requires `OPENROUTER_API_KEY` in env; absent key
⇒ adapter no-op (log + return None), signals simply not emitted.

## Open Questions

- [ ] Exact OpenRouter free auto-select string / `reasoning` payload shape — confirm against
  live API during apply.
- [ ] `Source` for inferred signals: `PLATFORM` vs a dedicated inferred source (assumed `PLATFORM`).
