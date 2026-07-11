# Proposal: Aggregate User-Response Silence Detection

## Intent

Add auditable `conversation.silence_detected` evidence for prolonged user-response pauses. Today the event exists in the taxonomy but has no producer or payload contract. The first slice derives silence deterministically after a call ends, avoiding live-state ambiguity and overlap with agent latency metrics.

## Scope

### In Scope
- Detect interior assistant-to-user gaps of **at least 6 seconds** from `end-of-call-report` turn timing.
- Emit at most one aggregated event per call with the qualifying interval count and sufficient audit data.
- Preserve retry-safe idempotency and C1 append-only semantics: ingestion-ordered `sequence_number`, chronologically meaningful `timestamp`.

### Out of Scope
- User-to-assistant latency, live detection/intervention, terminal silence, and `silence-timed-out`.
- Pre-first-turn or post-last-turn gaps and guessed results from incomplete timing.

## Capabilities

### New Capabilities
- `conversation-silence-detection`: Post-terminal, deterministic detection and aggregation of qualifying user-response silence intervals.

### Modified Capabilities
- None.

## Approach

Reuse the isolated post-terminal enrichment pipeline. Consolidate report messages into trustworthy turn boundaries, evaluate only consecutive assistant-to-user transitions, and aggregate gaps meeting the inclusive 6-second policy. Append one canonical event when the count is positive; repeated processing must resolve to the same identity. The event timestamp represents the detected conversation chronology even though persistence occurs after session termination.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/src/adapters/rest/vapi_mapping.py` | Modified | Preserve and normalize report turn boundaries. |
| `backend/src/application/use_cases/` | New | Detect, aggregate, and record silence evidence. |
| `backend/src/domain/session.py` | Modified | Permit the post-terminal canonical append. |
| `backend/src/infrastructure/celery/tasks.py` | Modified | Invoke isolated silence derivation. |
| `backend/tests/` | Modified | Add strict-TDD boundary, aggregation, ordering, and retry tests. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Fragmented or malformed timing misstates gaps | Medium | Consolidate deterministically; skip untrustworthy boundaries. |
| Duplicate events on webhook redelivery | Medium | Stable identity plus conflict-safe persistence. |
| Confusion with agent latency | Low | Restrict transitions to assistant-to-user only. |

## Rollback Plan

Disable/remove the post-terminal invocation and recorder. Existing append-only events remain historical evidence; no destructive migration is required.

## Dependencies

- Reliable `artifact.messages` start/end timing in Vapi `end-of-call-report`.
- Existing terminal enrichment, canonical event persistence, and idempotent append mechanisms.

## Success Criteria

- [ ] One event records the total qualifying interior pauses per call; zero qualifying pauses produce no event.
- [ ] Exactly 6 seconds qualifies; terminal and user-to-assistant gaps never qualify.
- [ ] Redelivery creates no duplicate, and chronological timestamps coexist with ingestion-ordered sequences.
