# Design: Real-time Speaking Indicator

## Technical Approach

Extend the existing best-effort active-session channel (Redis hash → `ws.py` 2s poll-push → `useActiveSessions`) with live speaking state. No new transport, no canonical persistence. `speech-update` already maps to `CONVERSATION_TURN_STARTED/ENDED` (with `Source.AGENT|USER`) and `user-interrupted` to `CONVERSATION_INTERRUPTION_DETECTED` in `vapi_mapping.py`. The gap: `update_active_state` ignores those event types, so the state never reaches the store. We add branches that read-modify-write the stored snapshot and serialize two new fields end to end.

## Architecture Decisions

| Decision | Choice | Rejected alternative | Rationale |
|---|---|---|---|
| Snapshot fields | Add `speaking_role: str \| None = None`, `last_interruption_at: datetime \| None = None` (defaulted) | Separate Redis keys / new hash | Defaults keep decode backward-compatible; one field per session stays atomic-per-write |
| Merge strategy | Read-modify-write the existing hash field; **skip if session absent** | `mark_active` full replace | Turn events lack `agent_id`; must not clobber lifecycle fields nor create partial snapshots |
| Store API | Two intent methods: `set_speaking_role(session_id, role\|None)`, `mark_interruption(session_id, at)` | One merge method with UNSET sentinels | Explicit intent; `turn_ended` clears (`None`) vs interruption leaving role untouched — no sentinel ambiguity |
| Role mapping | `command.source` → `AGENT→"agent"`, `USER→"user"`, else `None` | Re-parse raw payload | `Source` StrEnum values already are `"agent"/"user"`; command is the canonical hand-off |
| Stale fallback | Overwrite-on-next-event + clear on session end; treat as **live hint, not truth** | Server-side TTL / reaper task | Serialized per-call events self-correct; `mark_ended` already deletes the whole entry; TTL adds a timer for a non-authoritative signal |
| Concurrency | Atomic server-side merge/upsert via Lua (`EVAL`) scripts (HGET→cjson mutate→HSET in one round trip) | Client-side HGET→decode→HSET or read-modify-write across separate calls (non-atomic) | Two concurrent cross-field updates on the same session (e.g. `set_speaking_role` from speech-update racing `mark_interruption` from user-interrupted) could otherwise interleave and lose one of the updates — not cosmetic, since it could silently drop the interruption stamp or revert a role change. `_merge` is atomic (single EVAL, no client-visible read/write gap) for `set_speaking_role`/`mark_interruption`. `SESSION_STARTED` preservation uses the same pattern via a dedicated `upsert_lifecycle` EVAL (HGET→cjson mutate→HSET), so a resent `status-update` can no longer race a concurrent `set_speaking_role`/`mark_interruption` and lose it either — it never calls `list_active()`/HGETALL, so it stays O(1) per session and single-session-scoped (no cross-session blast radius) |

## Data Flow

    speech-update / user-interrupted
        │  (vapi.py webhook → map_vapi_event)
        ▼
    IngestEventCommand(event_type, source, timestamp)
        │  update_active_state()
        ▼
    Redis hash "active_sessions"  ── HGET field → merge JSON → HSET (skip if absent)
        │  ws.py list_active() every 2s
        ▼
    WebSocket JSON[]  →  useActiveSessions  →  ActiveSessionsPanel

## File Changes

| File | Action | Description |
|---|---|---|
| `application/ports/active_sessions.py` | Modify | Add two defaulted snapshot fields; add `set_speaking_role` + `mark_interruption` to `ActiveSessionStore` Protocol |
| `infrastructure/redis/active_sessions.py` | Modify | Implement the two methods (HGET→merge→HSET, no-op if absent); extend `_encode`/`_decode` (decode via `.get`); add 3 branches to `update_active_state` |
| `adapters/rest/ws.py` | Modify | Serialize `speaking_role` and `last_interruption_at` in `_to_dict` |
| `frontend/src/lib/api/types.ts` | Modify | Extend `ActiveSession` type |
| `frontend/src/components/ActiveSessionsPanel.tsx` | Modify | Render indicator states |
| backend + frontend tests | Create/Modify | Strict TDD |

## Interfaces / Contracts

`update_active_state` new branches:

```python
elif command.event_type is EventType.CONVERSATION_TURN_STARTED:
    await store.set_speaking_role(command.call_id, _role_from_source(command.source))
elif command.event_type is EventType.CONVERSATION_TURN_ENDED:
    await store.set_speaking_role(command.call_id, None)
elif command.event_type is EventType.CONVERSATION_INTERRUPTION_DETECTED:
    await store.mark_interruption(command.call_id, command.timestamp)
```

WebSocket per-session JSON (additions in **bold**):

```json
{ "session_id": "...", "agent_id": "...", "status": "active", "started_at": "...",
  "speaking_role": "agent" | "user" | null,
  "last_interruption_at": "2026-07-10T20:10:04+00:00" | null }
```

Frontend type:

```ts
export interface ActiveSession {
  session_id: string; agent_id: string; status: string; started_at: string;
  speaking_role: "agent" | "user" | null;
  last_interruption_at: string | null;
}
```

Frontend render (per `<li>`): `agent` → green pulse + "Agent speaking"; `user` → blue pulse + "User speaking"; `null` → neutral "Idle"; if `last_interruption_at` within a short client window (~4s of now) → amber "User interrupted" badge. Purely derived from the pushed fields; no new state machine.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | `update_active_state` maps turn_started/ended/interruption to store calls; `_role_from_source` | Fake store, assert calls |
| Unit | `set_speaking_role`/`mark_interruption` merge, no-op when absent, idempotent repeats, other fields preserved | Fake/real redis client |
| Unit | `_encode`/`_decode` round-trip incl. null + legacy field-less JSON | Direct |
| Integration | `ws.py` `_to_dict` includes new fields | Snapshot |
| Frontend | Panel renders each indicator state + interruption window | RTL |

## Migration / Rollout

No migration. Defaulted fields make existing Redis entries decode cleanly; revert is field + branch removal. Lifecycle and raw landing untouched.

## Open Questions

- [ ] Confirm `speech-update` + `user-interrupted` are in the assistant's **serverMessages** subscription (blocks live behavior, not the code).
- [ ] Interruption badge decay window (~4s) is a UX guess — confirm with product.
- [ ] Out-of-order `turn_ended` after a newer `turn_started` could briefly clear a live speaker (accepted as cosmetic best-effort).
