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

## Review Workload Forecast (Slice A)

| Metric | Estimate |
|---|---|
| Files touched (prod) | 3 (`vapi_mapping.py`, `vapi.py`, `active_sessions.py`) |
| Files touched (docs) | 1 (`vapi-event-coverage.md`, one-row edit) |
| Test files touched | 3-4 (`test_vapi_mapping.py`, `test_vapi_webhook.py`, `test_vapi_webhook_ingestion.py`; possibly a new/extended `active_sessions` test module) |
| Estimated changed lines | ~180-260 (classifier + constants ~50 lines; 2-line `_resolve` change; 2-line enqueue widening; 2-line active-store widening; test tables + assertions dominate the diff) |
| Stays under 400-line budget | Yes |
| Chained PRs needed | No — this is already the first of the two chained PRs defined in the design (PR-1 of 2); no further split needed within Slice A |
| Decision needed before apply | No — scope, file list, and TDD order are fully pinned by spec + design; proceed directly to `sdd-apply` |

---

# Tasks — Slice B: `session.evaluation_triggered` (PR-2, chained on PR-1)

Scope: post-terminal domain append, `RecordEvaluationTriggered` use case, the
repository port + idempotent marker-append implementation, the partial unique
index (migration + ORM mirror), Celery task wiring at evaluation start, the
remaining coverage-doc row, and tests. Depends on PR-1 (Slice A) merged.

Strict TDD: every behavior task is RED (failing test) → GREEN (minimal code) →
REFACTOR (if needed), in that order. Do not write production code before its
failing test exists. Float assertions in tests MUST use `pytest.approx(...)`,
never bare `==`, on any `float` comparison (`raw_value`, `score_*`) — the
external PR checker rejects float `==`.

## 0. Pre-flight — confirm the current Alembic head

- [x] 0.1 Run `cd backend && uv run alembic heads` and confirm the single head
      is `8e3c03e687de` (per design D-migration). Do NOT hardcode this value
      in the new migration without this check — if the head differs, use the
      actual head as `down_revision`.

## 1. Domain — `Session.append_marker()`

- [x] 1.1 RED — `backend/tests/test_domain_session.py`: add tests for
      `append_marker`:
      - appending `EventType.SESSION_EVALUATION_TRIGGERED` to an `ENDED`
        session returns an `Event` with `sequence_number == len(events) + 1`
        (continuing the existing sequence) and leaves `status == ENDED` and
        `ended_at` unchanged.
      - same for a `FAILED` session (`status` stays `FAILED`, `ended_at`
        unchanged).
      - appending to an `ACTIVE` session raises `SessionClosedError`.
      - appending a non-marker `event_type` (e.g. `EventType.SESSION_ENDED`)
        raises `DomainError` (or the chosen exception type — confirm against
        `src/domain/exceptions.py`).
      Confirm all fail (`append_marker` does not exist yet).
      _Spec: "Evaluation-triggered marker at task start" — both scenarios
      ("Evaluation start is recorded for an ended session" / "... failed
      session")._
- [x] 1.2 GREEN — implement `Session.append_marker()` in
      `backend/src/domain/session.py` per the design: module-level
      `_MARKER_EVENTS = frozenset({EventType.SESSION_EVALUATION_TRIGGERED})`,
      guard on `status is ACTIVE` (raise `SessionClosedError`), guard on
      `event_type not in _MARKER_EVENTS` (raise the domain error), assign
      `sequence_number = len(self.events) + 1`, append, return the `Event`,
      and do NOT touch `status`/`ended_at`. Run pytest, confirm 1.1 passes.
- [x] 1.3 REFACTOR (if needed) — no behavior change.

## 2. Application — port method + `RecordEvaluationTriggered` use case

- [x] 2.1 RED — new `backend/tests/test_record_evaluation_triggered.py`: a
      fake/stub `GovernanceRepository` capturing calls; assert
      `RecordEvaluationTriggered(repo).execute(session, timestamp)`:
      - calls `session.append_marker(SESSION_EVALUATION_TRIGGERED, PLATFORM,
        timestamp, payload={})` (verify via the returned/appended event on
        the session, not by mocking the domain method).
      - calls `repo.append_marker_event(event)` exactly once with that event.
      Confirm it fails (`RecordEvaluationTriggered` and
      `append_marker_event` do not exist).
      _Spec: "Evaluation-triggered marker at task start"; "Event schema" —
      `source = platform`, `payload MAY be empty`._
- [x] 2.2 GREEN — add `append_marker_event(self, event: Event) -> None: ...`
      to the `GovernanceRepository` Protocol in
      `backend/src/application/ports/governance_repository.py`. Create
      `backend/src/application/use_cases/record_evaluation_triggered.py` with
      the `RecordEvaluationTriggered` class per the design (constructor takes
      the repository; `execute(session, timestamp)` calls
      `session.append_marker(...)` then `await self._repo.append_marker_event(event)`).
      Run pytest, confirm 2.1 passes.
- [x] 2.3 REFACTOR (if needed).

## 3. ORM mirror of the partial unique index (test-suite dependency — read before skipping)

**Why this is NOT optional, unlike the design's "optionally mirror" note:**
`backend/tests/conftest.py`'s `db_session` fixture creates the schema via
`Base.metadata.create_all` — it does NOT run Alembic migrations. If the
partial unique index only exists in the migration, every test in this slice
that exercises `ON CONFLICT ... index_where=...` will fail in the test suite
with "no unique or exclusion constraint matching" because the index is
genuinely absent from the test DB. The ORM mirror is therefore load-bearing
for Strict TDD here, not cosmetic.

- [x] 3.1 RED — `backend/tests/test_governance_repository.py`: add a test
      that inserts two `SESSION_EVALUATION_TRIGGERED` events for the same
      `session_id` directly against the DB (or via `append_marker_event`
      called twice, once this exists — see section 4) and asserts only one
      row is persisted. This will fail with a raw DB error (no matching
      constraint) until 3.2 lands.
- [x] 3.2 GREEN — in `backend/src/infrastructure/db/models.py`, add
      `__table_args__` to `EventModel` with a partial unique `Index`:
      ```python
      __table_args__ = (
          Index(
              "uq_events_session_marker",
              "session_id",
              "event_type",
              unique=True,
              postgresql_where=text(
                  "event_type IN ('session.evaluation_triggered', 'session.failed')"
              ),
          ),
      )
      ```
      Import `Index` and `text` from `sqlalchemy`. The predicate string MUST
      exactly match the migration's (section 5) for both to describe the same
      constraint. Run pytest, confirm 3.1 passes.

## 4. Repository — idempotent marker append

- [x] 4.1 RED — `backend/tests/test_governance_repository.py`: add
      `test_append_marker_event_persists_a_single_row` — given a session
      already `ENDED` (via `save_session`), call
      `repo.append_marker_event(event)` for a
      `SESSION_EVALUATION_TRIGGERED` event, commit, and assert
      `repo.get_session(...)` reloads it among the session's events with the
      expected `sequence_number`. Confirm it fails (`append_marker_event` not
      implemented on `SqlAlchemyGovernanceRepository` yet — only the Protocol
      stub from 2.2 exists).
- [x] 4.2 RED (idempotency) — same file: add
      `test_append_marker_event_is_idempotent_on_conflict` — call
      `repo.append_marker_event(event)` twice with the same `session_id` +
      `event_type` (same or different `event_id`), commit, and assert only
      one row exists for that `(session_id, event_type)` pair. Confirm it
      fails until 4.3 lands (also depends on 3.2's index existing).
      _Spec: "Idempotent marker events" — "Evaluation task retry does not
      duplicate the marker"._
- [x] 4.3 RED (no session rewrite) — same file: add a test that calls
      `append_marker_event` on an `ENDED` session's marker event and asserts
      the session's `status`/`ended_at` are unchanged after reload (proving
      the repo method does not call `save_session`/`merge`). This can be
      folded into 4.1's assertions if simpler.
- [x] 4.4 GREEN — implement `append_marker_event` on
      `SqlAlchemyGovernanceRepository`
      (`backend/src/infrastructure/repositories/governance_repository.py`)
      per the design: `pg_insert(EventModel).values(**_event_values(event))
      .on_conflict_do_nothing(index_elements=["session_id", "event_type"],
      index_where=EventModel.event_type.in_([EventType.SESSION_EVALUATION_TRIGGERED.value,
      EventType.SESSION_FAILED.value]))`, then `await
      self._session.execute(stmt)`. Reuse the existing `_event_values`
      helper. Do NOT call `save_session` or touch `SessionModel`. Run pytest,
      confirm 4.1-4.3 pass.
- [x] 4.5 REFACTOR (if needed).

## 5. Migration — partial unique index (DB-authoritative, out-of-band deploy)

- [x] 5.1 Create `backend/alembic/versions/<hash>_add_session_marker_uniqueness.py`
      with `down_revision` set to the head confirmed in step 0.1 (expected
      `8e3c03e687de`). `upgrade()` creates
      `uq_events_session_marker` on `events(session_id, event_type)` with
      `postgresql_where` matching **exactly** the same predicate string used
      in 3.2's ORM mirror (`event_type IN ('session.evaluation_triggered',
      'session.failed')`). `downgrade()` drops the index. No test runs this
      migration directly (tests use `create_all`), so verify by inspection
      that the predicate strings in 3.2 and 5.1 are byte-identical.
- [x] 5.2 Document the out-of-band deploy caveat inline as a migration
      docstring/comment: the server starts without running migrations
      (commit `36aa530`), so this index MUST be applied manually
      (`alembic upgrade head` against the target DB) **before** this slice is
      deployed, or the `ON CONFLICT` insert in `append_marker_event` will
      raise in production.

## 6. Celery task — emit the marker at evaluation start

- [x] 6.1 RED — `backend/tests/test_build_evidences_task.py`: add
      `test_task_records_evaluation_triggered_marker_before_building_evidences`
      — given a session already `ENDED` (persisted via `save_session` +
      commit, same pattern as existing tests in this file), call
      `build_session_evidences_async(session_id)`, then reload the session
      via the repository and assert exactly one
      `SESSION_EVALUATION_TRIGGERED` event is present with `source ==
      Source.PLATFORM` and a `sequence_number` continuing the prior events.
      Confirm it fails (task does not emit the marker yet).
      _Spec: "Evaluation-triggered marker at task start" — both scenarios._
- [x] 6.2 RED (retry idempotency) — same file: add
      `test_task_retry_does_not_duplicate_evaluation_triggered_marker` —
      call `build_session_evidences_async(session_id)` twice for the same
      session and assert only one `SESSION_EVALUATION_TRIGGERED` event
      exists after both runs. Confirm it fails until 6.3 lands.
      _Spec: "Idempotent marker events" — "Evaluation task retry does not
      duplicate the marker"._
- [x] 6.3 RED (failure-closed: marker survives evidence-build failure) —
      same file: add a test that forces `build_evidences` (or
      `add_evidences`/`add_report`) to raise after the marker step (monkeypatch
      or a session with data that fails evidence building, if such a case
      exists; otherwise monkeypatch `build_evidences` to raise), and asserts
      the `SESSION_EVALUATION_TRIGGERED` event is still persisted (i.e. the
      marker's own commit already landed) even though the task itself
      raises/propagates. Confirm it fails until 6.4's own-commit ordering
      lands.
      _Design D5: marker survives evidence/scoring failure; Spec:
      "Failure-closed event processing"._
- [x] 6.4 GREEN — in `backend/src/infrastructure/celery/tasks.py`, inside
      `build_session_evidences_async`, right after `get_session` returns a
      non-`None` session and before `build_evidences(...)`:
      ```python
      await RecordEvaluationTriggered(repository).execute(
          governance_session, datetime.now(UTC)
      )
      await session.commit()  # marker durable regardless of evidence outcome
      ```
      Import `RecordEvaluationTriggered` and `datetime, UTC`. Keep the
      existing `evidences -> add_evidences -> report -> add_report ->
      commit` sequence unchanged after this. Run pytest, confirm 6.1-6.3
      pass and the existing tests in this file still pass.
- [x] 6.5 Add an INFO log line on successful marker insert (per design
      section 7): `"session.evaluation_triggered recorded: session={}"`.
      No test required for log content unless the repo already asserts on
      log capture elsewhere; keep consistent with existing logging style in
      `tasks.py`/`vapi.py`.
- [x] 6.6 REFACTOR (if needed).

## 7. Documentation — coverage doc row update

- [x] 7.1 Update `docs/design/vapi-event-coverage.md` row 12
      (`session.evaluation_triggered`): change "Inferred by platform logic"
      row's "Vapi webhook that currently produces it" from "None" to "N/A —
      platform-emitted marker (not from a Vapi webhook)" and "Current status
      / next step" from "Pending platform event when automatic evaluation
      starts." to "Implemented. Appended post-terminal at the start of
      `build_session_evidences_async`; see `RecordEvaluationTriggered` in
      `backend/src/application/use_cases/record_evaluation_triggered.py` and
      `Session.append_marker` in `backend/src/domain/session.py`."
      _Spec: "Event coverage documentation stays current" — scenario
      "Coverage doc reflects the new events" (evaluation_triggered half)._

## 8. Verify (matches CI)

- [x] 8.1 Run the focused test set first:
      `cd backend && uv run pytest tests/test_domain_session.py tests/test_record_evaluation_triggered.py tests/test_governance_repository.py tests/test_build_evidences_task.py -v`
      — confirm all new and existing tests are green.
- [x] 8.2 Run the full CI-equivalent sequence from `backend/`:
      - `uv run ruff check .`
      - `uv run ruff format --check .`
      - `uv run mypy src tests`
      - `uv run pytest`
      All green before considering the slice done.
- [x] 8.3 Confirm no float `==` assertions were introduced in any new test
      (`grep -n "== 0.0\|== 1.0" backend/tests/test_*.py` as a sanity check,
      or eyeball the new test files) — use `pytest.approx(...)` for every
      float comparison.
- [x] 8.4 Confirm the changed file list matches Slice B's scope: `session.py`,
      `governance_repository.py` (port + impl), `record_evaluation_triggered.py`
      (new), `models.py`, the new Alembic revision, `tasks.py`,
      `vapi-event-coverage.md`, plus the five test files touched above. No
      Slice A files were re-touched beyond what section 3/4 requires.
- [x] 8.5 Note in the PR description (per `cognitive-doc-design` /
      `work-unit-commits` skills): this is PR-2 of 2, chained on the merged
      Slice A PR (`stacked-to-main`); call out the **out-of-band migration
      caveat** from section 5.2 explicitly as a deploy prerequisite.

## Review Workload Forecast (Slice B)

| Metric | Estimate |
|---|---|
| Files touched (prod) | 5 (`session.py`, `governance_repository.py` port, `governance_repository.py` impl, `record_evaluation_triggered.py` new, `models.py`, `tasks.py` — 6 counting the port/impl as the same file with two edits) |
| Files touched (migration) | 1 (new Alembic revision) |
| Files touched (docs) | 1 (`vapi-event-coverage.md`, one-row edit) |
| Test files touched | 4 (`test_domain_session.py` extended, `test_record_evaluation_triggered.py` new, `test_governance_repository.py` extended, `test_build_evidences_task.py` extended) |
| Estimated changed lines | ~220-320 (domain method ~35 lines; port +1 line; use case ~20 lines; repo method ~15 lines; ORM index ~12 lines; migration ~25 lines; task wiring ~10 lines; test additions dominate at ~150-200 lines given 3 idempotency/ordering scenarios) |
| Stays under 400-line budget | Yes, with margin |
| Chained PRs needed | No further split — this is already PR-2 of 2 in the design's chained plan; `stacked-to-main` on top of the merged Slice A |
| Decision needed before apply | No — scope, file list, TDD order, and the ORM-mirror requirement (section 3, discovered during tasks review, not in the design's "optional" framing) are fully pinned; proceed directly to `sdd-apply` |
