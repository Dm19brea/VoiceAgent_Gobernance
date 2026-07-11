# Design: Derive conversation content events from end-of-call-report

## Technical Approach

`conversation.agent_response` / `conversation.user_input` have no working canonical
source (the `conversation-update` → `_resolve_role_message` branch returns `None`).
Per the SETTLED design doc, we derive both roles from the authoritative
`end-of-call-report` `message.artifact.messagesOpenAIFormatted` and **append them
post-terminal** (append-only, C1) in `build_session_evidences_async`, mirroring the
proven `RecordSystemObservation` idempotency pattern. Source of the report is the
session's own terminal event payload (`map_vapi_event` retains full `message`,
incl. `artifact`, in the `SESSION_ENDED/FAILED` event payload). No live-view change.

## Architecture Decisions

### Decision: Post-terminal content-append domain API
**Choice**: Add `Session.append_conversation_content(event_type, source, timestamp, payload, event_id)`
gated to `_CONVERSATION_CONTENT_EVENTS = {CONVERSATION_AGENT_RESPONSE, CONVERSATION_USER_INPUT}`,
requiring `status is not ACTIVE`, assigning `sequence_number = len(self.events)+1`.
**Alternatives**: extend `append_system_observation` to permit content types; relax `record()`.
**Rationale**: mirrors `append_marker`/`append_system_observation` exactly (same
invariant, same signature shape). Keeps conversation vs. system semantics separate;
`record()` must keep rejecting non-ACTIVE to protect lifecycle.

### Decision: Persist via `append_event`, not `append_marker_event`
**Choice**: reuse `repository.append_event` (ON CONFLICT `event_id` DO NOTHING).
**Alternatives**: `append_marker_event`.
**Rationale**: `append_marker_event` relies on the partial unique index on
`(session_id, event_type)` — fine for a single marker, but content has **many** rows
per session per type. `append_event` dedups on the UUID5 `event_id`, matching
`RecordSystemObservation`.

### Decision: Idempotency identity (UUID5)
**Choice**: new `RecordConversationContent` use case with `canonical_content_event_id`,
`schema_version = "conversation-content/v1"`, UUID5(NAMESPACE_URL) over canonical JSON
`{event_type, identity, schema_version, session_id}` where
`identity = {role, content_sha256, turn_index}`.
- `content_sha256` = sha256 of `unicodedata.normalize("NFC", content).strip()`.
- `turn_index` = zero-based enumerate index within `messagesOpenAIFormatted` (stable
  across redelivery/re-run; disambiguates repeated identical content).
**Rationale**: identical to `record_system_observation.py` (timestamps + raw ids
excluded). Redelivery/re-run recomputes the same `event_id` → `existing` short-circuit
or ON CONFLICT no-op. New `ConversationContentCommand` dataclass (role + content +
turn_index) keeps type safety separate from `SystemObservationCommand`.

### Decision: Parsing + timestamp derivation
**Choice**: iterate `messagesOpenAIFormatted` in order; `assistant`→
`CONVERSATION_AGENT_RESPONSE`/`Source.AGENT`, `user`→`CONVERSATION_USER_INPUT`/`Source.USER`,
skip `system`. Timestamp: positional role-matched zip against `artifact.messages`
(`bot`→assistant, `user`→user, skip `system`), consuming `messages[].time` in order for
the matching role. **Fallback** when timing is missing/misaligned: use
`session.ended_at` (post-terminal, always known). `timestamp` is chronological;
`sequence_number` is provenance/append order.
**Rationale**: `messagesOpenAIFormatted` lacks timing; `messages` carries it but is a
different (bot/user) view. Positional role-matched consumption is the pragmatic,
crash-free alignment; the fallback keeps derivation total.

### Decision: Where it runs
**Choice**: a best-effort, isolated-transaction step `_record_conversation_content(...)`
in `build_session_evidences_async`, **after** the evidence/report commit and the
evaluation observations — same shape as `_record_evaluation_observations` (own engine,
NullPool, swallow+log). `RecordConversationContent` does one `get_session_for_update`
then loops (compute id → check `session.events` → append → `append_event`).
**Rationale**: content is derived audit enrichment, not an input to current scoring
(the path was dead, so `build_evidences` never consumed it). Isolating it after the
critical path guarantees it cannot block or corrupt ingestion/evaluation. Marker stays
first (own commit); content stays last.

### Decision: `conversation-update` removal
**Choice**: delete lines 253-254 in `_resolve`; `conversation-update` falls to `None`
(raw landing only). `transcript` (251-252) and `speech-update` (247-248) untouched.
**Rationale**: dead branch; removal is landing-only with zero regression to other types.

## Data Flow

    terminal webhook ─→ SESSION_ENDED/FAILED event (payload.artifact retained)
          │
    build_session_evidences.delay(call_id)
          │
    build_session_evidences_async:
      RecordEvaluationTriggered (own commit)
      build_evidences → report (commit)
      _record_evaluation_observations (isolated)
      _record_conversation_content (isolated)  ← NEW
          │ parse artifact.messagesOpenAIFormatted (+messages timing)
          └─→ RecordConversationContent → append_conversation_content → append_event (UUID5 dedup)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `domain/session.py` | Modify | Add `_CONVERSATION_CONTENT_EVENTS` + `append_conversation_content` |
| `application/commands.py` | Modify | Add `ConversationContentCommand` |
| `application/use_cases/record_conversation_content.py` | Create | `canonical_content_event_id` + `RecordConversationContent` (batch loop) |
| `adapters/rest/vapi_mapping.py` | Modify | Remove dead `conversation-update` branch; add `derive_conversation_content(report)` mapper |
| `infrastructure/celery/tasks.py` | Modify | Add `_record_conversation_content` isolated step + call after eval observations |
| `docs/design/vapi-event-coverage.md` | Modify | Note content events now sourced post-terminal |
| `backend/tests/...` | Create/Modify | Unit + integration coverage |

## Interfaces / Contracts

```python
_CONVERSATION_CONTENT_EVENTS = frozenset(
    {EventType.CONVERSATION_AGENT_RESPONSE, EventType.CONVERSATION_USER_INPUT}
)

@dataclass(frozen=True, slots=True)
class ConversationContentCommand:
    session_id: str
    event_type: EventType
    source: Source
    timestamp: datetime          # report messages[].time or ended_at fallback
    role: str                    # "assistant" | "user"
    content: str
    turn_index: int
    # identity = {role, content_sha256(NFC+strip), turn_index}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | mapper role→event/source, skip system, timestamp zip + fallback, UUID5 stability | pure fns over fixture report |
| Unit | `append_conversation_content` rejects ACTIVE / wrong type; sequence_number | domain tests |
| Integration | post-terminal append writes both roles; re-run/redelivery = 0 duplicates | DB round-trip via task |
| Integration | `conversation-update` webhook → raw only, no domain event; transcript unaffected | mapping regression |
| Edge | empty/missing `messagesOpenAIFormatted`, no assistant/user roles, missing artifact | asserts no-op |

## Migration / Rollout

No migration. Purely additive events + one dead-branch removal. Historical sessions
gain content only if the terminal report is reprocessed (out of scope).

## Open Questions

- [ ] Confirm `artifact.messagesOpenAIFormatted`/`messages` survive intact in the
  terminal event JSONB payload for real reports (not just the sample call).
- [ ] Content-vs-evidence ordering: if a future evidence builder needs content,
  the isolated step must move **before** `build_evidences` (documented risk, not this change).
- [ ] Very large calls: `RecordConversationContent` reloads once then loops in-memory
  (O(N) appends); acceptable for typical call sizes — revisit if calls exceed ~hundreds of turns.
