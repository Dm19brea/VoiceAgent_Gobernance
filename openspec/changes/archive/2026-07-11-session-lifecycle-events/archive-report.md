# Archive Report: session-lifecycle-events

**Date Archived**: 2026-07-11
**Change**: `session-lifecycle-events`
**Archive Location**: `openspec/changes/archive/2026-07-11-session-lifecycle-events/`

---

## Verification Status

**Verdict**: PASS — feature verified implemented in `main` at archive time.

**Implementation evidence (verified in code):**
- `session.failed` classification: `backend/src/adapters/rest/vapi_mapping.py` (`classify_terminal_event` → `EventType.SESSION_FAILED` for error `endedReason`, fail-safe default to `session.ended`).
- Evaluation enqueue widened to any terminal event: `backend/src/adapters/rest/vapi.py` (`_TERMINAL_EVENTS = (SESSION_ENDED, SESSION_FAILED)`).
- `session.evaluation_triggered` post-terminal marker: `backend/src/application/use_cases/record_evaluation_triggered.py` (`session.append_marker` + `append_marker_event`).
- Idempotent marker persistence: partial unique index migration `backend/alembic/versions/d851eabb9809_add_session_marker_uniqueness.py` scoped to `event_type IN ('session.evaluation_triggered', 'session.failed')`, with `ON CONFLICT DO NOTHING`.

---

## Specs Merged Into Source of Truth

### Main Spec Created

**Delta Spec**: `session-lifecycle-events` (11 requirements)
**Main Spec Location**: `openspec/specs/session-lifecycle-events/spec.md`
**Action**: Created (no prior main spec existed; the change's `spec.md` is a complete capability spec)
**Requirements Merged**: terminal event classification, mutual exclusivity, status-update never closes a session, evaluation-triggered marker, failed sessions still evaluated, terminal-derived evidence/scoring distinctions, idempotent markers, event schema, failure-closed processing, and coverage-doc currency.

---

## Archive Contents

- `proposal.md`
- `design.md`
- `tasks.md`
- `spec.md`

---

## Source of Truth Updated

- `openspec/specs/session-lifecycle-events/spec.md` — Platform-emitted `session.failed`
  and `session.evaluation_triggered` events closing the canonical `session.*` taxonomy,
  decoupled from Vapi evals.

**Status**: Archived. Feature is live in `main`.
