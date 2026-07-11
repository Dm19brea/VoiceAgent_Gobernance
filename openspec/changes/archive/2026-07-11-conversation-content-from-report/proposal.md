# Proposal: Derive conversation content events from end-of-call-report

## Intent

Today `conversation.agent_response` / `conversation.user_input` have **no working
canonical source**: `_resolve` routes `conversation-update` to `_resolve_role_message`,
which returns `None` (no top-level `role`), so the mapping is dead and no content events
are ever persisted. The audit record therefore lacks the actual dialogue turns. The
SETTLED design (`docs/design/conversation-events-from-end-of-call-report.md`) resolves
this: derive both content events **post-terminal** from the authoritative
`end-of-call-report`, and demote `conversation-update` to raw-landing-only.

## Scope

### In Scope
- Derive `conversation.agent_response` (role=assistant) and `conversation.user_input`
  (role=user) from `end-of-call-report` `message.artifact.messagesOpenAIFormatted`,
  appended in the post-terminal path (`build_session_evidences_async`), like the existing
  `session.evaluation_triggered` marker.
- Field semantics (design C1, append-only): `sequence_number` = ingestion/provenance order
  (monotonic per session, existing uniqueness invariant); `timestamp` = true chronological
  order from the report's `messages[].time`. Consumers order by `timestamp`.
- Make `conversation-update` explicitly **landing-only**: remove the dead
  `_resolve` → `_resolve_role_message` mapping path.
- Retry-safe idempotency: reprocessing the report or a Vapi redelivery must not duplicate
  content events — reuse the UUID5 stable-identity approach used for system observations.

### Out of Scope
- `conversation.interruption_detected` (stays real-time `user-interrupted`), `turn_started`/
  `turn_ended` (live-only, not persisted), `silence_detected`/`topic_change`/`goal_*`
  (deferred). Any live-view / WebSocket change.

## Capabilities

### New Capabilities
- `conversation-content-events`: post-terminal derivation of `agent_response`/`user_input`
  from the end-of-call-report, with `timestamp`-based ordering and retry-safe identity.

### Modified Capabilities
- None (no existing conversation spec; taxonomy doc updated, not a spec).

## Approach

Add a mapper (in `vapi_mapping.py`) that expands the report's `messagesOpenAIFormatted` into
per-turn content commands, pairing each with its `messages[].time` timestamp. In
`build_session_evidences_async`, after the evaluation marker, append these via the same
post-terminal, best-effort, isolated-transaction pattern used for system observations. Give
content events a UUID5 identity over stable fields (session_id, event_type, role, normalized
content, turn index) so redelivery/retry is a no-op. Extend the domain append path to accept
these post-terminal content events (analogous to `append_system_observation`). Remove the
`conversation-update` mapping line so it lands raw only.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/src/adapters/rest/vapi_mapping.py` | Modified | New report→content mapper; drop `conversation-update` mapping. |
| `backend/src/infrastructure/celery/tasks.py` | Modified | Append content events post-terminal. |
| `backend/src/application/use_cases/` | New/Modified | Content-event recorder with UUID5 identity. |
| `backend/src/domain/session.py` | Modified | Allow post-terminal content-event append. |
| `docs/design/vapi-event-coverage.md` | Modified | Flip planned→implemented. |
| `backend/tests/` | Modified | Strict-TDD coverage. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Duplicate events on redelivery/retry | Med | UUID5 stable identity + existing-event short-circuit. |
| `sequence_number` collision (past deploy break) | Med | C1 append-only; monotonic `len(events)+1`. |
| Missing/misaligned `messages[].time` | Med | Fall back to report/receipt time; keep provenance order. |
| Empty/partial `messagesOpenAIFormatted` | Low | No-op when absent; raw report retained. |

## Rollback Plan

Revert the mapper, tasks hook, recorder, and domain append change. Restore the
`conversation-update` mapping line if needed. Raw landing and lifecycle are untouched, so no
data migration; already-derived events remain valid rows.

## Dependencies

- `end-of-call-report` carries `artifact.messagesOpenAIFormatted` and `messages[].time`
  (confirmed in the design's sample-call analysis).

## Success Criteria

- [ ] Content events appear post-terminal for both roles with report `timestamp`.
- [ ] Reprocessing / Vapi redelivery creates zero duplicates.
- [ ] `conversation-update` no longer produces a canonical event (raw only).
- [ ] Consumers can reconstruct the timeline by ordering on `timestamp`.
- [ ] Backend tests pass.
