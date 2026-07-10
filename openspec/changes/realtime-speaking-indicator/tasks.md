# Tasks: Real-time Speaking Indicator

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~220-280 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Phase 1: Snapshot Fields (Foundation)

- [x] 1.1 RED — `backend/tests/test_active_session_store.py`: add test asserting legacy field-less JSON decodes with `speaking_role=None`, `last_interruption_at=None`.
- [x] 1.2 GREEN — `backend/src/application/ports/active_sessions.py`: add `speaking_role: str | None = None` and `last_interruption_at: datetime | None = None` to `ActiveSessionSnapshot`.
- [x] 1.3 RED — `backend/tests/test_active_session_store.py`: add round-trip test for `_encode`/`_decode` with populated `speaking_role` + `last_interruption_at`.
- [x] 1.4 GREEN — `backend/src/infrastructure/redis/active_sessions.py`: extend `_encode`/`_decode` for the two new fields (decode via `.get` for backward compatibility).

## Phase 2: Store Intent Methods

- [x] 2.1 RED — `backend/tests/test_active_session_store.py`: test `set_speaking_role(session_id, "agent")` merges onto existing snapshot without touching other fields; `set_speaking_role(session_id, None)` clears it.
- [x] 2.2 RED — same file: test `set_speaking_role`/`mark_interruption` are no-ops (no exception, no entry created) when the session is absent.
- [x] 2.3 GREEN — `backend/src/infrastructure/redis/active_sessions.py`: implement `set_speaking_role(session_id, role: str | None)` — HGET, decode, merge, HSET; skip if absent.
- [x] 2.4 RED — test `mark_interruption(session_id, at)` sets `last_interruption_at` and leaves `speaking_role` untouched.
- [x] 2.5 GREEN — implement `mark_interruption(session_id, at: datetime)` with same read-modify-write/no-op pattern.
- [x] 2.6 GREEN — `backend/src/application/ports/active_sessions.py`: add both method signatures to the `ActiveSessionStore` Protocol.

## Phase 3: Webhook Wiring (update_active_state)

- [x] 3.1 RED — `backend/tests/test_active_state_wiring.py`: test `CONVERSATION_TURN_STARTED` with `Source.AGENT` calls `set_speaking_role(call_id, "agent")`; with `Source.USER` calls `set_speaking_role(call_id, "user")`.
- [x] 3.2 RED — same file: test `CONVERSATION_TURN_ENDED` (any source) calls `set_speaking_role(call_id, None)`.
- [x] 3.3 RED — same file: test `CONVERSATION_INTERRUPTION_DETECTED` calls `mark_interruption(call_id, command.timestamp)` and does not call `set_speaking_role`.
- [x] 3.4 RED — same file: test a `CONVERSATION_TURN_ENDED` with no prior `TURN_STARTED` still clears cleanly (no-op safe via store no-op behavior; scenario "dropped turn_ended does not stick").
- [x] 3.5 GREEN — `backend/src/adapters/rest/vapi.py` (`update_active_state`): add the three branches per design's `Interfaces / Contracts` mapping (role derived from `command.source`: AGENT->"agent", USER->"user", else None).
- [x] 3.6 RED — same file: test session end (`SESSION_ENDED`/`SESSION_FAILED`) still deletes the snapshot entirely (regression check — confirms existing `mark_ended` behavior clears speaking state too).

## Phase 4: WebSocket Serialization

- [x] 4.1 RED — `backend/tests/test_active_sessions_ws.py`: test `_to_dict` output includes `speaking_role` (string|null) and `last_interruption_at` (ISO8601 string|null) for a snapshot with values set.
- [x] 4.2 RED — same file: test `_to_dict` on a snapshot without these fields set still serializes `null` for both (backward-compat scenario).
- [x] 4.3 GREEN — `backend/src/adapters/rest/ws.py` (`_to_dict`): add `speaking_role` and `last_interruption_at` (`.isoformat()` if present else `None`) to the serialized payload.

## Phase 5: Frontend Types & Rendering

- [x] 5.1 GREEN — `frontend/src/lib/api/types.ts`: extend `ActiveSession` with `speaking_role: "agent" | "user" | null` and `last_interruption_at: string | null`.
- [x] 5.2 RED — `frontend/src/components/ActiveSessionsPanel.test.tsx`: test row renders "Agent speaking" when `speaking_role === "agent"`, "User speaking" when `"user"`, "Idle" when `null`.
- [x] 5.3 RED — same file: test amber "User interrupted" badge renders when `last_interruption_at` is within ~4s of now, and does not render when older or null.
- [x] 5.4 GREEN — `frontend/src/components/ActiveSessionsPanel.tsx`: render the three speaking states + interruption badge, derived purely from pushed fields (no client state machine), per design.

## Phase 6: Verification

- [x] 6.1 Run backend test suite (`test_active_session_store.py`, `test_active_state_wiring.py`, `test_active_sessions_ws.py`) — confirm all 7 spec requirements/11 scenarios are covered and passing.
- [x] 6.2 Run frontend test suite (`ActiveSessionsPanel.test.tsx`) — confirm indicator + badge scenarios pass.
- [x] 6.3 Manual smoke check: confirm no new canonical event types, no `conversation-update` usage, no persistence beyond the Redis active-session snapshot (scope boundary check per spec requirement 7).
