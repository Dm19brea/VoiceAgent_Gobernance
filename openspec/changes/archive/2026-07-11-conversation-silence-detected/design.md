# Design: Aggregate User-Response Silence Detection

## Technical Approach

Derive one deterministic aggregate after the terminal report is persisted. The Vapi adapter converts fragmented `artifact.messages` into trustworthy turn boundaries; a provider-independent pure detector evaluates only adjacent assistant-to-user turns. A separate best-effort Celery step records the result through the existing post-terminal conversation-signal path.

## Architecture Decisions

| Decision | Choice and rationale | Rejected alternative |
|---|---|---|
| Turn boundaries and indices | Extend consolidation to return `TimedTurn(role, turn_index, started_at, ended_at)`. `turn_index` is assigned monotonically to consolidated raw bot/user groups and is the single index source for both content and silence events. Each group uses only its first fragment's `time` and final fragment's `endTime`. The formatted assistant/user role sequence must match the consolidated sequence exactly; count or role mismatch fails silence derivation closed. Missing/invalid/non-finite boundaries remain `None`. | Formatted-message indices or first-fragment end times can misalign fragmented assistant turns. |
| Detection boundary | Add a pure `detect_user_response_silence(turns, policy)` application function. It accepts normalized turns, never raw Vapi payloads, and returns `SilenceAggregate | None`. | Embedding policy in Celery or the adapter couples transport parsing to business rules. |
| Aggregate timestamp | Timestamp the event at the `ended_at` (user response start) of the last qualifying interval. This is the latest chronological evidence boundary represented by the complete aggregate; sequence remains append order. | First threshold crossing predates later intervals; persistence time loses conversation chronology. |
| Identity and version lifecycle | UUID5 inputs are `session_id`, event type, and immutable version `assistant-user-interior-gap/v1`; computed details are excluded. The maintainer owns version bumps. Evidence-altering parser, consolidation, alignment, threshold, exclusion, timestamp, payload, identity, or detector changes require a new version; output-neutral refactors do not. New versions apply only to unprocessed calls. Existing evidence is never recalculated, backfilled, superseded, or migrated. | Reusing a version changes historical meaning; reprocessing creates competing evidence. |
| Persistence | Reuse `ConversationSignalCommand`, row locking, and conflict-safe insertion. After locking the session, the recorder searches events by type; if any `conversation.silence_detected` exists, regardless of UUID/version, it returns it without derivation or append. Otherwise it appends the versioned UUID5 once. Thus each session has at most one silence event across versions and concurrent workers. Add silence to the post-terminal signal allowlist. | UUID-only conflicts permit one event per version; a new path duplicates sequence behavior. |

## Data Flow

```text
terminal event artifact.messages
  -> Vapi fragment consolidation
  -> TimedTurn[]
  -> pure silence detector (>= 6000 ms)
  -> zero: no command | one+: one ConversationSignalCommand
  -> locked Session append -> conflict-safe event insert
```

`_record_conversation_silence` runs in its own engine/transaction and catches/logs all failures. It is invoked independently after content derivation and before the LLM judge; malformed timing produces no command and cannot block content, scoring, or judge signals.

## Interfaces / Contracts

```python
SilencePolicy(threshold_ms=6000, detector_version="assistant-user-interior-gap/v1")
SilenceInterval(assistant_turn_index, user_turn_index, started_at, ended_at, duration_ms)
SilenceAggregate(count, intervals, detected_at)
```

Canonical payload:

```json
{
  "count": 1,
  "threshold_ms": 6000,
  "detector_version": "assistant-user-interior-gap/v1",
  "intervals": [
    {"assistant_turn_index": 1, "user_turn_index": 2, "started_at": "...", "ended_at": "...", "duration_ms": 7200}
  ],
  "identity": "<deterministic UUID5>"
}
```

Contract invariant: `count == len(intervals)`. Intervals are chronological and `detected_at == intervals[-1].ended_at`.

Only direct adjacent assistant-to-user transitions with finite, non-negative, ordered boundaries qualify. User-to-assistant, pre/post-call gaps, and assistant turns without a subsequent user response are absent by construction. `endedReason=silence-timed-out` never creates an interval; earlier genuine interior responses remain independently auditable.

## File Changes

| File | Action | Description |
|---|---|---|
| `backend/src/application/use_cases/detect_conversation_silence.py` | Create | Pure policy, interval, and aggregation logic. |
| `backend/src/adapters/rest/vapi_mapping.py` | Modify | Preserve first-start/final-end turn boundaries and map report timing. |
| `backend/src/domain/session.py` | Modify | Allow silence as a post-terminal conversation signal. |
| `backend/src/infrastructure/celery/tasks.py` | Modify | Add isolated derivation/recording step. |
| `backend/tests/test_conversation_silence_detection.py` | Create | Pure boundary, threshold, exclusions, aggregation, malformed timing tests. |
| `backend/tests/test_conversation_content_mapping.py` | Modify | Fragment boundary consolidation/alignment tests. |
| `backend/tests/test_record_conversation_signals.py` | Modify | Stable identity, allowlist, and redelivery tests. |
| `backend/tests/test_governance_repository.py` | Modify | Concurrent same-session lock/conflict/sequence proof. |
| `backend/tests/test_build_evidences_task.py` | Modify | Pipeline persistence, chronology/sequence, and failure isolation tests. |

## Testing Strategy

Strict TDD: RED pure detector tests first; GREEN mapping/domain tests; then integration. Unit coverage proves 5999/6000 ms, exclusions, malformed boundaries, and that a multi-gap aggregate uses the last qualifying user-response start as timestamp. Mapping tests prove fragmented turns share indices with content and role/count mismatch yields no silence. Integration proves redelivery idempotency, later sequence with earlier timestamp, and failure isolation. A repository test runs two independent same-session workers concurrently and asserts one silence event, one unique next sequence, and no sequence collision under the session-row lock plus event-ID conflict handling.

## Migration / Rollout

No migration or feature flag is required: the enum already exists and payload is JSON. Roll back by removing the isolated task invocation; historical append-only events remain valid.

## Open Questions

None.
