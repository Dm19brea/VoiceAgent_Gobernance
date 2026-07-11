# Tasks: LLM-judge post-terminal conversation signals

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~420-500 (6 new/changed src files + adapter + tests) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full change (domain -> port/adapter -> use case -> mapping -> wiring -> cleanup) | PR 1 | Cohesive slice; tests included per phase |

## Phase 1: Domain — append_conversation_signal

- [x] 1.1 RED: `backend/tests/test_domain_session.py` — tests for `Session.append_conversation_signal`: appends `CONVERSATION_TOPIC_CHANGE`/`CONVERSATION_GOAL_ACHIEVED`/`CONVERSATION_GOAL_FAILED` when status ENDED/FAILED; raises `SessionClosedError` when ACTIVE; raises `DomainError` for non-member `event_type`; does not mutate `status`/`ended_at` (spec: "Signal derivation does not mutate session lifecycle").
- [x] 1.2 GREEN: `backend/src/domain/session.py` — add `_SIGNAL_EVENTS = frozenset({EventType.CONVERSATION_TOPIC_CHANGE, EventType.CONVERSATION_GOAL_ACHIEVED, EventType.CONVERSATION_GOAL_FAILED})` and `Session.append_conversation_signal(event_type, source, timestamp, payload, event_id=None)`, mirroring `append_conversation_content`.

## Phase 2: Judge port + DTOs

- [x] 2.1 RED: `backend/tests/test_openrouter_judge.py` (new) — test `OpenRouterConversationJudge.evaluate(transcript)` returns a `JudgeVerdict` for a valid strict-JSON reply (fake HTTP transport).
- [x] 2.2 GREEN: `backend/src/application/ports/conversation_judge.py` (new) — `ConversationJudge` Protocol (`evaluate(transcript: str) -> JudgeVerdict | None`) and `JudgeVerdict` frozen dataclass (`topic_change_count`, `topics`, `topic_reason`, `goal_achieved`, `goal_reason`).
- [x] 2.3 RED: `backend/tests/test_openrouter_judge.py` — test malformed/unparseable JSON reply is treated as a failed attempt (returns `None` after exhausting retries), per spec "Malformed judge output counts as a failed attempt".
- [x] 2.4 RED: `backend/tests/test_openrouter_judge.py` — test retry policy: first attempt times out, second succeeds -> returns verdict, no more than 2 attempts made (spec "Judge succeeds on retry within the attempt budget").
- [x] 2.5 RED: `backend/tests/test_openrouter_judge.py` — test all 3 attempts fail (mix of timeout/rate-limit/malformed) -> returns `None`, no error raised (spec "Judge exhausts retries and yields no signals").
- [x] 2.6 GREEN: `backend/src/adapters/llm/openrouter_judge.py` (new) — `OpenRouterConversationJudge` implementing `ConversationJudge`: reads `OPENROUTER_API_KEY`/base URL/timeout from `Settings`; MAX 3 attempts with exponential backoff (0.5s/1s/2s); per-attempt timeout; strict-JSON schema validation (`topic_change.count/topics/reason?`, `goal.verdict/reason`); malformed reply or missing key -> logs and returns `None`, never raises.

## Phase 3: Transcript builder + verdict mapping

- [x] 3.1 RED: `backend/tests/test_vapi_mapping.py` — test `build_judge_transcript(report_message)`: builds a structured transcript string from `artifact.messagesOpenAIFormatted` (same source as `derive_conversation_content`), skipping `system` entries.
- [x] 3.2 GREEN: `backend/src/adapters/rest/vapi_mapping.py` — implement `build_judge_transcript(report_message)`.
- [x] 3.3 RED: `backend/tests/test_vapi_mapping.py` — test `verdict_to_signal_commands(verdict, session_id, timestamp)`: `topic_change_count > 0` -> one `ConversationSignalCommand` for `CONVERSATION_TOPIC_CHANGE` with `payload={count, topics, reason?}`; `topic_change_count == 0` -> no topic-change command; `goal_achieved=True` -> one `CONVERSATION_GOAL_ACHIEVED` command, never both goal commands (spec "mutually-exclusive goal verdict").
- [x] 3.4 GREEN: `backend/src/adapters/rest/vapi_mapping.py` — implement `verdict_to_signal_commands(verdict, session_id, timestamp)`; `application/commands.py` — add `ConversationSignalCommand` dataclass (`session_id`, `event_type`, `source: Source.PLATFORM`, `timestamp`, `identity_fields`, `payload`).

## Phase 4: Idempotent identity + RecordConversationSignals use case

- [x] 4.1 RED: `backend/tests/test_record_conversation_signals.py` (new) — test `canonical_signal_event_id`: same `{event_type, identity, schema_version, session_id}` -> same UUID5 across calls; topic identity keyed only on `{count}` (not `topics`/`reason`); goal identity keyed only on `{verdict}` (not `reason`); different count/verdict -> different id.
- [x] 4.2 GREEN: `backend/src/application/use_cases/record_conversation_signals.py` (new) — `_IDENTITY_SCHEMA_VERSION = "conversation-signal/v1"`; `canonical_signal_event_id(command)` via `uuid5(NAMESPACE_URL, ...)`, mirroring `record_conversation_content.py`.
- [x] 4.3 RED: `backend/tests/test_record_conversation_signals.py` — test `RecordConversationSignals.execute(session_id, commands)`: appends events via `session.append_conversation_signal` + `repository.append_event`; existing `event_id` short-circuits as no-op (spec "Reprocessing the same report is idempotent", "Provider redelivers the end-of-call-report webhook").
- [x] 4.4 GREEN: implement `RecordConversationSignals.execute` — single `get_session_for_update`, loop over commands with existing-event check.
- [x] 4.5 Test: session not found -> no-op, logs warning (mirror `record_conversation_content.py`).

## Phase 5: Wiring into build_session_evidences_async

- [x] 5.1 RED: celery task test (`backend/tests/test_tasks.py` or equivalent) — `_record_conversation_signals(session_id, message)` runs AFTER `_record_conversation_content` completes, is isolated (own `NullPool` engine, try/except + `logger.exception`), and a judge failure/exception does NOT raise out of `build_session_evidences_async` nor affect content events (spec "Judge exhausts retries and yields no signals" — content events intact).
- [x] 5.2 RED: test end-to-end success path with `FakeConversationJudge` — writes at most 1 `topic_change` + 1 goal event (achieved XOR failed); reprocessing same report yields zero new signal events.
- [x] 5.3 RED: test info-only transcript (`FakeConversationJudge` returns `goal_achieved=True`, `topic_change_count=0`) -> only `CONVERSATION_GOAL_ACHIEVED` appended, no topic event (spec "Information-only call defaults to goal_achieved").
- [x] 5.4 GREEN: `backend/src/infrastructure/celery/tasks.py` — add `_record_conversation_signals(session_id, message)` following `_record_conversation_content` shape (own engine/session/repository, `OpenRouterConversationJudge`, `build_judge_transcript`, `verdict_to_signal_commands`, `RecordConversationSignals`, try/except swallow+log); call it in `build_session_evidences_async` immediately after `_record_conversation_content`.
- [x] 5.5 GREEN: `backend/src/infrastructure/config.py` — add `openrouter_api_key`, `openrouter_base_url`, `openrouter_timeout_seconds` settings fields.

## Phase 6: Verification

- [x] 6.1 Run `uv run mypy .` in `backend/` and fix type errors introduced by new files/dataclasses.
- [x] 6.2 Run the full backend test suite (`uv run pytest`) and confirm all spec scenarios are covered and green: judge post-terminal timing, aggregated topic_change, achieved/failed/info-only goal verdict, retry success, retry exhaustion (zero signals, content intact, no raise), malformed-output-as-failed-attempt, idempotent reprocessing, redelivery no-dup, lifecycle non-mutation.
