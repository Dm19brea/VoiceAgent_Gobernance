# Tasks: Derive conversation content events from end-of-call-report

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~350-420 (5 new/changed src files + 4 test files) |
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
| 1 | Full change (domain -> use case -> wiring -> cleanup) | PR 1 | Cohesive slice; tests included per phase |

## Phase 1: Domain — append_conversation_content

- [x] 1.1 RED: `backend/tests/test_domain_session.py` — add tests for `Session.append_conversation_content`: appends `CONVERSATION_AGENT_RESPONSE`/`CONVERSATION_USER_INPUT` when status ENDED/FAILED; raises `SessionClosedError` when ACTIVE; raises `DomainError` for any other `event_type`; `sequence_number = len(events)+1`; does not mutate `status`/`ended_at`.
- [x] 1.2 GREEN: `backend/src/domain/session.py` — add `_CONVERSATION_CONTENT_EVENTS = frozenset({EventType.CONVERSATION_AGENT_RESPONSE, EventType.CONVERSATION_USER_INPUT})` and `Session.append_conversation_content(event_type, source, timestamp, payload, event_id=None)`, mirroring `append_system_observation` (reject ACTIVE, reject non-member `event_type`, assign `sequence_number`, optional `event_id`).
- [x] 1.3 REFACTOR: confirm no duplication with `append_system_observation`; keep both explicit per design decision 1 (no merge).

## Phase 2: Idempotent identity + command

- [x] 2.1 `backend/src/application/commands.py` — add `ConversationContentCommand` dataclass (`session_id`, `event_type`, `source`, `timestamp`, `role: str`, `content: str`, `turn_index: int`, `payload: dict[str, Any]`).
- [x] 2.2 RED: `backend/tests/test_record_conversation_content.py` (new) — test `canonical_content_event_id`: same `{role, content, turn_index}` (after NFC-normalize + strip) -> same UUID5 across two calls; different `turn_index` or different content -> different id; whitespace/case-in-content difference that survives NFC-normalize -> different id (case is NOT normalized, only NFC+strip).
- [x] 2.3 GREEN: `backend/src/application/use_cases/record_conversation_content.py` (new) — `_IDENTITY_SCHEMA_VERSION = "conversation-content/v1"`; `content_sha256(content) = sha256(unicodedata.normalize("NFC", content).strip())`; `canonical_content_event_id(command) -> UUID` via `uuid5(NAMESPACE_URL, ...)` over `{event_type, identity: {role, content_sha256, turn_index}, schema_version, session_id}`, `json.dumps(sort_keys=True, ensure_ascii=True)`, mirroring `record_system_observation.py:26-45`.

## Phase 3: RecordConversationContent use case

- [x] 3.1 RED: `backend/tests/test_record_conversation_content.py` — test `RecordConversationContent.execute(session_id, commands)`: given N `ConversationContentCommand`s, appends N events via `session.append_conversation_content` and calls `repository.append_event` once per event; existing `event_id` in `session.events` short-circuits (idempotent no-op, matches redelivery/reprocessing scenarios); returns list of resulting `Event`s.
- [x] 3.2 GREEN: implement `RecordConversationContent.execute` in `record_conversation_content.py` — single `repository.get_session_for_update(session_id)`, loop over commands: compute `event_id`, check `session.events` for existing match, else `session.append_conversation_content(...)` + `repository.append_event(event)`.
- [x] 3.3 Test: session not found -> no-op, logs warning (mirror `record_system_observation.py:63-69`).

## Phase 4: Parsing + timestamp alignment

- [x] 4.1 RED: `backend/tests/test_vapi_mapping.py` (or new `test_conversation_content_mapping.py`) — test `derive_conversation_content(message)` (new function in `vapi_mapping.py`): given `messagesOpenAIFormatted` with N alternating `user`/`assistant` entries and a matching `messages[]` array, returns N `ConversationContentCommand`-shaping tuples in report order with correct `event_type`/`Source` (assistant->`CONVERSATION_AGENT_RESPONSE`/`Source.AGENT`, user->`CONVERSATION_USER_INPUT`/`Source.USER`), `system` entries skipped and not counted toward `turn_index`.
- [x] 4.2 RED: test for CONSOLIDATED-vs-FRAGMENTED misalignment — `messagesOpenAIFormatted` has one entry per turn while `artifact.messages[]` has multiple bot fragments per assistant turn (e.g. 2 fragment rows for one assistant turn); assert timestamp alignment consumes only ONE `messages[]` time per `messagesOpenAIFormatted` turn (role-run grouping: consecutive same-role `messages[]` fragments consolidate into a single turn before positional matching), not a naive 1:1 zip.
- [x] 4.3 RED: test for fallback — turn has no matching `messages[]` entry (missing/exhausted) -> timestamp falls back to `session.ended_at`.
- [x] 4.4 GREEN: implement `_consolidate_messages_by_turn(messages)` helper in `vapi_mapping.py` that collapses consecutive same-role `messages[]` fragments into one time-per-turn list (first fragment's `time`, or documented choice), then role-matched positional zip against `messagesOpenAIFormatted` (skipping `system`) to assign `timestamp`; missing/exhausted alignment falls back to `session.ended_at`.
- [x] 4.5 GREEN: implement `derive_conversation_content(report_message, session_ended_at)` returning ordered `(event_type, source, timestamp, role, content, turn_index, payload)` tuples per design decision 4.

## Phase 5: Wiring into build_session_evidences_async

- [x] 5.1 RED: celery task test (in existing celery task test file, e.g. `backend/tests/test_tasks.py` or equivalent) — `_record_conversation_content(session_id, message)` step runs AFTER evidence/report commit and `_record_evaluation_observations`, is isolated (own `NullPool` engine, try/except + `logger.exception`), and a failure inside it does NOT raise out of `build_session_evidences_async` nor roll back the evaluation report.
- [x] 5.2 RED: test that empty/missing `messagesOpenAIFormatted` produces zero content events and no error (spec scenario "Empty or missing messagesOpenAIFormatted is a no-op").
- [x] 5.3 RED: test that content events land with `sequence_number` after all existing events including `session.evaluation_triggered` marker (spec scenario "Content events land after in-call events by sequence").
- [x] 5.4 GREEN: `backend/src/infrastructure/celery/tasks.py` — add `_record_conversation_content(session_id, message)` following `_record_evaluation_observations` shape (own engine/session/repository, `RecordConversationContent`, try/except swallow+log); call it in `build_session_evidences_async` after the existing `_record_evaluation_observations` call, sourcing `message` from the session's terminal event payload (`report` / `artifact`).
- [x] 5.5 Test: reprocessing the same report (re-running the step for the same session) creates no duplicate content events (spec scenario "Reprocessing the same report is idempotent").

## Phase 6: conversation-update cleanup

- [x] 6.1 RED: `backend/tests/test_vapi_mapping.py` — add/confirm test that a `conversation-update` webhook maps to `None` via `map_vapi_event` (no canonical event), while `transcript` and `speech-update` mappings are unaffected (unchanged behavior).
- [x] 6.2 GREEN: `backend/src/adapters/rest/vapi_mapping.py` — delete the `if vapi_type == "conversation-update": return _resolve_role_message(message)` branch (lines ~253-254) from `_resolve`, so it falls through to `None`.

## Phase 7: Verification

- [x] 7.1 Update `docs/design/vapi-event-coverage.md` to reflect `conversation-update` as landing-only and content events as report-derived.
- [x] 7.2 Run `uv run mypy .` in `backend/` and fix any type errors introduced by new files/dataclasses.
- [x] 7.3 Run the full backend test suite (`uv run pytest`) and confirm all 9 spec scenarios are covered and green.
