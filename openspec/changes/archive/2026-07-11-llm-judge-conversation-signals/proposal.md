# Proposal: LLM-judge post-terminal conversation signals

## Intent

The platform derives raw dialogue turns from the `end-of-call-report`, but has **no
outcome/quality signals**: nothing states whether the call drifted across topics or
whether the caller's problem was actually resolved. Reviewers must read full transcripts
to judge outcomes. This change adds a **post-terminal LLM judge** that reads the full
transcript and emits canonical governance signals, reusing the existing idempotent
post-terminal pipeline rather than inventing parallel machinery.

## Scope

### In Scope
- Post-terminal judge over the full transcript (built from the same
  `artifact.messagesOpenAIFormatted` used by `derive_conversation_content`), emitting:
  - `conversation.topic_change` — **one** event/call, payload `{count, topics[], reason?}`.
  - `conversation.goal_achieved` **or** `conversation.goal_failed` — a **single**
    mutually-exclusive verdict/call, payload `{reason}`.
- OpenRouter chat-completions integration (free model, key from env var), returning
  structured output a new mapper parses into the events above.
- Retry-safe UUID5 canonical identity (stable fields, never timestamps/raw ids), reusing
  the `RecordConversationContent` approach so report reprocessing / Vapi redelivery is a no-op.
- **Failure isolation**: judge timeout / rate-limit / malformed output MUST NOT block or
  corrupt the existing content derivation; signals are best-effort.

### Out of Scope
- Real-time / live judging during the call.
- Per-problem or per-goal breakdowns; per-turn discrete topic-change events.
- Paid LLM providers.
- Frontend/report UI (possible follow-up).

## Capabilities

### New Capabilities
- `conversation-signal-events`: post-terminal LLM-derived topic-change and goal verdict
  signals with retry-safe identity and failure isolation.

### Modified Capabilities
- None (no existing conversation-signal spec).

## Approach

In `build_session_evidences_async`, after `_record_conversation_content`, add a best-effort
`_record_conversation_signals` step. A new mapper (alongside `derive_conversation_content`)
builds a structured transcript string + the three questions, calls OpenRouter, and parses
the reply into signal commands. A `RecordConversationSignals` use case (analog of
`RecordConversationContent`) assigns UUID5 identity over stable fields and appends via a new
`append_conversation_signal` domain path (analog of `append_conversation_content`, gated by a
new `_SIGNAL_EVENTS` frozenset). The three `EventType` values already exist in
`domain/enums.py`, so no taxonomy additions are required.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/src/adapters/rest/vapi_mapping.py` | Modified | Transcript builder + signal-reply parser. |
| `backend/src/adapters/.../openrouter_*` | New | OpenRouter client (env-key, timeout, best-effort). |
| `backend/src/application/commands.py` | Modified | `ConversationSignalCommand`. |
| `backend/src/application/use_cases/` | New | `RecordConversationSignals` (UUID5 identity). |
| `backend/src/domain/session.py` | Modified | `_SIGNAL_EVENTS` + `append_conversation_signal`. |
| `backend/src/infrastructure/celery/tasks.py` | Modified | Best-effort `_record_conversation_signals`. |
| `backend/tests/` | Modified | Strict-TDD coverage. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Free model rate-limit/timeout/downtime | High | Isolated try/except; content derivation unaffected; retry-safe re-run. |
| Malformed/non-parseable judge output | High | Strict parse + validation; skip signals on failure, no partial writes. |
| Duplicate signals on redelivery/retry | Med | UUID5 stable identity + existing-event short-circuit. |
| LLM verdict quality/hallucination | Med | Require `reason`; single verdict; treat as inferred evidence. |

## Rollback Plan

Revert the mapper, OpenRouter client, command, use case, domain append, and the tasks hook.
The judge step is additive and isolated; content derivation, raw landing, and lifecycle are
untouched, so no data migration. Already-derived signal rows remain valid.

## Dependencies

- `OPENROUTER_API_KEY` env var and network egress to `openrouter.ai`.
- `end-of-call-report` carries `artifact.messagesOpenAIFormatted` (already relied on).

## Success Criteria

- [ ] Each call emits at most one `topic_change` (count+topics) and exactly one goal verdict.
- [ ] Judge failures leave content events intact; task does not fail.
- [ ] Reprocessing / redelivery creates zero duplicate signals.
- [ ] Backend tests pass under strict TDD.

## Open Questions

- Reuse existing enum string `conversation.topic_change` (business wording said
  `topic_changed`)? Assumed **yes** — reuse existing canonical value.
- If a call has no clear goal (info-only), which verdict — or a no-op? (spec decision)
- Retry policy for the judge: inline best-effort only, or a bounded async retry? (design)
- Which specific free OpenRouter model id, and token/transcript-size limits? (design)
