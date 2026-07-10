# Proposal: Real-time Speaking Indicator for the Live Session View

## Intent

The live monitoring view only shows whether a session is active or closed. Supervisors
cannot see conversational state as it happens. This change upgrades the live surface to
show, in real time, **who is currently speaking** (agent vs user) and **when the user
interrupted the agent** — turning a status light into a live conversational-state channel.
Gap today: `speech-update` maps to `conversation.turn_started/ended`, but
`update_active_state` only reacts to session lifecycle events, so speaking state never
reaches the active-session store or the browser.

## Scope

### In Scope
- Extend `ActiveSessionSnapshot` with `speaking_role` (`assistant|user|null`) and
  `last_interruption_at` (`timestamp|null`).
- Update those fields in `update_active_state` when `speech-update`
  (`turn_started`/`turn_ended`) and `user-interrupted` (`interruption_detected`) arrive.
- Serialize the new fields through the WebSocket snapshot stream (`ws.py`) and the
  frontend `ActiveSession` type / live panel so the indicator renders without polling.

### Out of Scope
- Post-terminal derivation of `agent_response`/`user_input` from `end-of-call-report` (second change).
- Removing `conversation-update` as an event source; any taxonomy/canonical-persistence change.
- Persisting `turn_started`/`turn_ended` as canonical events — they stay LIVE-ONLY.

## Capabilities

### New Capabilities
- `live-speaking-indicator`: real-time speaking-state and interruption signal on the
  active-session live view, sourced from `speech-update` + `user-interrupted`.

### Modified Capabilities
- None.

## Approach

Raw landing and canonical ingestion are unchanged. In `update_active_state`, add
branches: on `turn_started` set `speaking_role` from the event source (agent/user); on
`turn_ended` clear it; on `interruption_detected` stamp `last_interruption_at`. Merge
these onto the existing stored snapshot (read-modify-write) instead of replacing it. The
WebSocket loop already streams snapshots every 2s, so enriching the serialized shape is
enough; the frontend reads the new fields and renders the indicator.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/src/application/ports/active_sessions.py` | Modified | Add snapshot fields (defaulted). |
| `backend/src/infrastructure/redis/active_sessions.py` | Modified | Update/encode speaking state in `update_active_state`. |
| `backend/src/adapters/rest/ws.py` | Modified | Serialize new fields. |
| `frontend/src/lib/api/types.ts` + live panel | Modified | Type + render indicator. |
| `backend/tests/`, `frontend` tests | Modified | Strict-TDD coverage. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `speech-update`/`user-interrupted` not in Vapi `serverMessages` | Med | Verify subscription; degrade to status-only. |
| Stale `speaking_role` if `turn_ended` missed | Med | Clear on session end; treat as best-effort live hint. |
| Read-modify-write races on the Redis snapshot | Low | Snapshot is best-effort, non-authoritative. |

## Rollback Plan

Revert the snapshot fields, `update_active_state` branches, and serialization. Defaulted
fields make the store backward-compatible; lifecycle behavior and raw landing are untouched.

## Dependencies

- `speech-update` and `user-interrupted` subscribed in the assistant's `serverMessages`.

## Success Criteria

- [ ] Live view shows agent/user speaking in real time from `speech-update`.
- [ ] User interruption surfaces on the live view from `user-interrupted`.
- [ ] No canonical persistence added for turn events; raw landing unchanged.
- [ ] Backend and frontend tests pass.
