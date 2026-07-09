# Tasks — Slice A: `session.failed` (PR-1)

Scope: `endedReason` classifier, wiring into `_resolve`, enqueue widening to the
terminal set, and the discovered `update_active_state` leak fix. No migration,
no marker infrastructure — that is Slice B (placeholder at the end).

Strict TDD: every behavior task is RED (failing test) → GREEN (minimal code) →
REFACTOR (if needed), in that order. Do not write production code before its
failing test exists.

## 1. Classifier — `classify_terminal_event`

- [x] 1.1 RED — `backend/tests/test_vapi_mapping.py`: add a parametrized test
      table for `classify_terminal_event(ended_reason)` covering:
      - normal reasons → `SESSION_ENDED` (`customer-ended-call`, `None`, `""`,
        non-string input, an unrecognized/unknown string)
      - error substrings → `SESSION_FAILED` (`*error*`, `*fault*`)
      - prefix families → `SESSION_FAILED` (`pipeline-*`,
        `call.start.error-*`, `call.in-progress.error-*`, `call-start-error-*`,
        `twilio-*`, `vonage-*`, `assistant-request-returned-*`)
      - contains-family → `SESSION_FAILED` (`*-voice-failed`,
        `*-transcriber-failed`, `*-transport-*`, `*-worker-*`)
      - explicit named failures → `SESSION_FAILED` (`llm-failed`,
        `pipeline-no-available-llm-model`,
        `phone-call-provider-closed-websocket`, `worker-shutdown`,
        `assistant-not-found`, `assistant-not-valid`,
        `assistant-request-failed`, `assistant-join-timed-out`)
      Run pytest, confirm all new cases fail (function does not exist yet).
      _Spec: "Terminal event classification from end-of-call-report" —
      scenarios "Normal hangup ends the session", "Error reason fails the
      session", "Transport/provider error fails the session", "Unknown reason
      defaults to normal end"._
- [x] 1.2 GREEN — implement `classify_terminal_event` in
      `backend/src/adapters/rest/vapi_mapping.py` per the design (pure
      function, module-level constants `_FAILURE_SUBSTRINGS`,
      `_FAILURE_PREFIXES`, `_FAILURE_REASONS`, `_FAILURE_CONTAINS`,
      `_FAILURE_PREFIXES_FAMILY`). Run pytest, confirm the 1.1 table passes.
- [x] 1.3 REFACTOR (if needed) — no behavior change; only clean up duplication
      between the constants and the classifier body if the GREEN step left any.

## 2. Wire the classifier into `_resolve`

- [x] 2.1 RED — `backend/tests/test_vapi_mapping.py` (or
      `test_vapi_webhook_ingestion.py`, whichever already exercises
      `map_vapi_event`/`_resolve` for `end-of-call-report`): add a test that
      `map_vapi_event` with `type="end-of-call-report"` and an error
      `endedReason` (e.g. `"pipeline-error-openai-llm-failed"`) returns a
      command with `event_type == EventType.SESSION_FAILED`, and that a normal
      `endedReason` still returns `SESSION_ENDED`. Confirm it fails against the
      current unconditional `SESSION_ENDED` return in `_resolve`.
      _Spec: same requirement as above; also "Event schema" — payload carries
      `ended_reason`._
- [x] 2.2 RED (payload) — extend the same test (or add one) asserting the
      `session.failed` command's `payload["report"]["ended_reason"]` matches
      the input `endedReason`, proving the report/payload assembly is
      untouched. Confirm it fails or is trivially true only once 2.3 lands —
      order this before 2.3's code change if it can fail meaningfully, else
      fold into 2.1.
- [x] 2.3 GREEN — change the `end-of-call-report` branch in `_resolve`
      (`backend/src/adapters/rest/vapi_mapping.py`) to
      `return (classify_terminal_event(message.get("endedReason")), Source.PLATFORM)`.
      Run pytest, confirm 2.1/2.2 pass and no existing `end-of-call-report`
      tests regress.

## 3. End-to-end: FAILED session via `Session.record()`

- [x] 3.1 RED — in `backend/tests/test_vapi_webhook_ingestion.py` (or the
      integration test that drives the webhook through `IngestEvent`), add a
      test: an active session receiving `end-of-call-report` with an error
      `endedReason` ends up with `status == SessionStatus.FAILED` after
      ingestion (reusing the existing `Session.record()` ACTIVE→FAILED
      transition — no domain change expected). Confirm it fails before 2.3, or
      confirm it now passes as a consequence of 2.3 if written after
      (sequence 1→2→3 as listed, so this should already be GREEN once
      section 2 lands; if so, skip the RED sub-step and record it directly as
      a regression/characterization test).
      _Spec: "Error reason fails the session" scenario; "Mutual exclusivity of
      terminal events" — second terminal event is rejected (existing
      `record()` guard, add a test if not already covered for FAILED)._
- [x] 3.2 RED — add a mutual-exclusivity test: a session already `FAILED` from
      a prior `end-of-call-report` receiving a second `end-of-call-report`
      does not change status and does not raise an unhandled state (matches
      existing `record()` guard behavior for `ENDED`, mirrored for `FAILED`).
      _Spec: "Second terminal event is rejected"._
- [x] 3.3 GREEN — no production code expected (reuses existing `record()`
      guard); if the test fails, this reveals a real gap — fix only what's
      needed in `Session.record()` to satisfy it, keeping the ACTIVE-only
      invariant intact.

## 4. Enqueue widening — evaluate failed sessions too

- [x] 4.1 RED — in `backend/tests/test_vapi_webhook.py` (webhook route level,
      mocking `build_session_evidences.delay`), add a test: a webhook that
      resolves to `SESSION_FAILED` still calls
      `build_session_evidences.delay(command.call_id)`. Confirm it fails
      against the current `command.event_type is EventType.SESSION_ENDED`
      check.
      _Spec: "Failed sessions are still evaluated" — scenario "A failed
      session is enqueued for evaluation"._
- [x] 4.2 GREEN — in `backend/src/adapters/rest/vapi.py`, introduce
      `_TERMINAL_EVENTS = (EventType.SESSION_ENDED, EventType.SESSION_FAILED)`
      and change the enqueue guard to
      `if command is not None and command.event_type in _TERMINAL_EVENTS:`.
      Run pytest, confirm 4.1 passes and the existing `SESSION_ENDED` enqueue
      test still passes.

## 5. Fix the active-store leak on FAILED sessions

- [x] 5.1 RED — add a unit test for `update_active_state` (new or existing
      test module for `active_sessions.py`) asserting that a command with
      `event_type == EventType.SESSION_FAILED` calls `store.mark_ended` (same
      as it already does for `SESSION_ENDED`). Confirm it fails against the
      current `elif command.event_type is EventType.SESSION_ENDED:` branch
      (FAILED currently falls through and does nothing).
      _Design: discovered bug, folded into Slice A ("a failed call must behave
      like a terminal call end-to-end"). No direct spec scenario, but supports
      "Failed sessions are still evaluated" intent and general terminal
      symmetry._
- [x] 5.2 GREEN — in `backend/src/infrastructure/redis/active_sessions.py`,
      widen the branch to
      `elif command.event_type in (EventType.SESSION_ENDED, EventType.SESSION_FAILED):`
      calling `await store.mark_ended(command.call_id)`. Run pytest, confirm
      5.1 passes and existing `SESSION_ENDED` active-store test still passes.

## 6. Documentation — coverage doc row update

- [x] 6.1 Update `docs/design/vapi-event-coverage.md`, row for `session.failed`:
      change "Vapi webhook that currently produces it" from "None currently
      promoted" to `end-of-call-report` (via `classify_terminal_event`), and
      "Current status / next step" from the pending note to "Implemented.
      Classified from `endedReason` on `end-of-call-report`; see
      `classify_terminal_event` in `backend/src/adapters/rest/vapi_mapping.py`."
      Leave the `session.evaluation_triggered` row untouched (Slice B).
      _Spec: "Event coverage documentation stays current" — scenario "Coverage
      doc reflects the new events" (session.failed half only; the
      evaluation_triggered half belongs to Slice B)._

## 7. Verify

- [x] 7.1 Run the focused test set:
      `cd backend && uv run pytest tests/test_vapi_mapping.py tests/test_vapi_webhook.py tests/test_vapi_webhook_ingestion.py tests/test_vapi_report_normalisation.py -v`
      (adjust invocation to match `backend/pyproject.toml`'s configured
      runner). All new and existing tests green.
- [x] 7.2 Run `ruff check backend/src/adapters/rest/vapi_mapping.py backend/src/adapters/rest/vapi.py backend/src/infrastructure/redis/active_sessions.py` (and `ruff format --check` if used in this repo).
- [x] 7.3 Run `mypy` (or the repo's configured type checker) against the same
      three files plus any touched test files.
- [x] 7.4 Confirm no changes were made outside Slice A's file list (`vapi_mapping.py`,
      `vapi.py`, `active_sessions.py`, the four test files above,
      `docs/design/vapi-event-coverage.md`).

## 8. Post-review fixes (fresh-context review of Slice A)

- [x] 8.1 RED — `backend/tests/test_evidence_builder.py`: add tests for a
      session terminating in `SESSION_FAILED` asserting an `ended_reason`
      evidence is produced and that the `session_duration_seconds` evidence's
      `source_events` includes the terminal event id. Confirm both fail
      against the `EventType.SESSION_ENDED`-only filter.
      _Spec: "Terminal-derived evidence and scoring treat session.failed the
      same as session.ended"._
- [x] 8.2 GREEN — introduce `TERMINAL_EVENT_TYPES = (SESSION_ENDED,
      SESSION_FAILED)` in `backend/src/domain/evidence_builder.py`, use it for
      the terminal-event lookup, and make the `session_completed` conclusion
      reflect a failed outcome when the terminal event is `SESSION_FAILED`.
- [x] 8.3 RED — `backend/tests/test_scoring_catalogue.py`: add a test that a
      failed session (`report={"ended_reason": "pipeline-error-openai-llm-failed"}`)
      yields a `clean_ending` metric with `raw_value == 0.0`. Confirm it fails
      because `_ended_reason` only scans `SESSION_ENDED`.
- [x] 8.4 GREEN — `backend/src/domain/scoring/catalogue.py`: reuse
      `TERMINAL_EVENT_TYPES` from `evidence_builder` in `_ended_reason` instead
      of the hardcoded `SESSION_ENDED` check.
- [x] 8.5 RED — `backend/tests/test_vapi_mapping.py`: add a test that an
      `endedReason` containing "default" (e.g.
      `"customer-selected-default-voice"`) classifies as `SESSION_ENDED`, and
      that `"vapifault-openai-llm-failed"` still classifies as
      `SESSION_FAILED`. Confirm the "default" case fails (bare `"fault"`
      substring false-positives).
- [x] 8.6 GREEN — `backend/src/adapters/rest/vapi_mapping.py`: replace bare
      `"fault"` with `"vapifault"` in `_FAILURE_SUBSTRINGS`.
- [x] 8.7 Verify — full `uv run pytest -q`, `uv run ruff check`, `uv run mypy`
      on all changed files; all green.

## 9. Regression fix — session_completed always emitted for failed sessions

The 8.x fix made the `session_completed` criterion appear for `SESSION_FAILED`
sessions too (only the conclusion text changed), which meant
`detect_blocking_flags` never raised `FLAG_SESSION_NOT_COMPLETED` for a failed
session (the flag check keys on the criterion name) and the `completion`
metric was awarded full marks. This section splits the criterion by outcome
and adds a dedicated blocking flag.

- [x] 9.1 RED — `backend/tests/test_evidence_builder.py`: add
      `test_failed_session_yields_session_failed_criterion_not_completed`
      asserting a `session_failed` criterion (not `session_completed`) is
      produced for a `SESSION_FAILED` terminal, with conclusion "The session
      failed". Confirm it fails against the current single-criterion
      implementation.
- [x] 9.2 GREEN — `backend/src/domain/evidence_builder.py`: emit
      `session_completed` only for `SESSION_ENDED`; emit a distinct
      `session_failed` criterion/evidence for `SESSION_FAILED`. Keep the
      terminal-aware `ended_reason` evidence and duration `source_events`
      unchanged (still keyed on `TERMINAL_EVENT_TYPES`).
- [x] 9.3 RED — `backend/tests/test_scoring_flags.py`: add
      `FLAG_SESSION_FAILED` tests — a `session_failed` evidence raises exactly
      `FLAG_SESSION_FAILED` and not `FLAG_SESSION_NOT_COMPLETED`. Confirm they
      fail (name doesn't exist yet / flag not raised).
- [x] 9.4 GREEN — `backend/src/domain/scoring/flags.py`: add
      `FLAG_SESSION_FAILED = "session_failed"`; raise it when the
      `session_failed` criterion is present; raise
      `FLAG_SESSION_NOT_COMPLETED` only when neither `session_completed` nor
      `session_failed` is present.
- [x] 9.5 RED — `backend/tests/test_scoring_catalogue.py`: add
      `test_failed_session_has_no_completion_metric` asserting `completion` is
      absent for a failed session while `clean_ending` stays `0.0`. Confirm it
      fails (completion currently awarded).
- [x] 9.6 GREEN — confirm `backend/src/domain/scoring/catalogue.py` needs no
      change (the `completion` gate on `session_completed` now naturally
      excludes failed sessions once 9.2 lands); re-run to confirm green.
- [x] 9.7 RED — `backend/tests/test_deterministic_evaluator.py`: add
      `test_failed_session_raises_flag_session_failed_and_result_is_failed`
      asserting the evaluator's `result` is `FAILED` and the only blocking
      flag is `FLAG_SESSION_FAILED` for a failed session. Confirm it passes
      once 9.2/9.4 land (evaluator already treats any non-empty flags list as
      forcing FAILED — no evaluator code change needed).
- [x] 9.8 Update `openspec/changes/session-lifecycle-events/spec.md`'s
      "Terminal-derived evidence and scoring..." requirement to describe the
      completion-criterion split and the new blocking flag semantics.
- [x] 9.9 Verify — full `uv run pytest -q`, `uv run ruff check`, `uv run mypy`
      on all changed files; all green. Do not commit.

## Downstream (not in this list) — Slice B placeholder

- [ ] `session.evaluation_triggered`: `Session.append_marker()`,
      `RecordEvaluationTriggered` use case, `GovernanceRepository.append_marker_event`
      port + SQLAlchemy implementation, partial unique index migration
      (`(session_id, event_type)` on the two marker types), `tasks.py` wiring
      with its own pre-evidence commit, remaining coverage-doc row, and tests.
      Depends on PR-1 (this slice) merged; the migration must be applied
      out-of-band before deploy.

## Review Workload Forecast

| Metric | Estimate |
|---|---|
| Files touched (prod) | 3 (`vapi_mapping.py`, `vapi.py`, `active_sessions.py`) |
| Files touched (docs) | 1 (`vapi-event-coverage.md`, one-row edit) |
| Test files touched | 3-4 (`test_vapi_mapping.py`, `test_vapi_webhook.py`, `test_vapi_webhook_ingestion.py`; possibly a new/extended `active_sessions` test module) |
| Estimated changed lines | ~180-260 (classifier + constants ~50 lines; 2-line `_resolve` change; 2-line enqueue widening; 2-line active-store widening; test tables + assertions dominate the diff) |
| Stays under 400-line budget | Yes |
| Chained PRs needed | No — this is already the first of the two chained PRs defined in the design (PR-1 of 2); no further split needed within Slice A |
| Decision needed before apply | No — scope, file list, and TDD order are fully pinned by spec + design; proceed directly to `sdd-apply` |
