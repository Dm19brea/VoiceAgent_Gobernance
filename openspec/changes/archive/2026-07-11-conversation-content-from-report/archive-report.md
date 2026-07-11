# Archive Report: conversation-content-from-report

**Date Archived**: 2026-07-11
**Change**: `conversation-content-from-report`
**Archive Location**: `openspec/changes/archive/2026-07-11-conversation-content-from-report/`
**Delivery**: Merged as PR #19 (`feat/conversation-content-from-report`)

---

## Verification Status

**Verdict**: PASS (feature merged to `main`)
**Spec Compliance**: All requirements covered by the tests that shipped with PR #19
(`backend/tests/test_conversation_content_mapping.py`,
`backend/tests/test_build_evidences_task.py`, `backend/tests/test_record_conversation_content.py`).

---

## Specs Merged Into Source of Truth

### Main Spec Created

**Delta Spec**: `conversation-content-events` (5 requirements)
**Main Spec Location**: `openspec/specs/conversation-content-events/spec.md`
**Action**: Created (no prior main spec existed; delta spec is a complete capability spec)
**Requirements Merged**:
1. Content events derived from end-of-call-report
2. Field semantics — provenance sequence, chronological timestamp
3. Post-terminal append does not mutate session lifecycle
4. Retry-safe idempotent identity
5. `conversation-update` is landing-only

---

## Archive Contents

- `proposal.md`
- `design.md`
- `tasks.md`
- `specs/conversation-content-events/spec.md`

---

## Source of Truth Updated

- `openspec/specs/conversation-content-events/spec.md` — Post-terminal derivation of
  `conversation.agent_response` / `conversation.user_input` from the
  `end-of-call-report` `messagesOpenAIFormatted`, replacing the dead
  `conversation-update` mapping path.

**Status**: Archived. Feature is live in `main`.
