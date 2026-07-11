# Emit the two platform-sourced session lifecycle events

Close the canonical session event taxonomy by emitting the two remaining session
events **from the platform itself**, fully decoupled from Vapi "evals":

- `session.evaluation_triggered` — recorded when the platform's OWN automatic
  evaluation of a finished session starts (`source = platform`).
- `session.failed` — recorded when a session terminates through an uncontrolled
  error rather than a normal hangup (`source = platform`).

This supersedes the abandoned `session-eval-events` direction. Vapi evals are a
mock-conversation testing framework with no webhook and no link to real sessions
(engram `#423`), so the `GET /eval/run/{id}` path is out of scope permanently.

## Why now

The canonical model (`TFM - Plataforma de Gobernanza para Agentes de Voz/3.1
Modelo de eventos.md`) defines four `session.*` events. Two are already emitted
(`session.started`, `session.ended`); the other two are declared in the code
(`EventType.SESSION_FAILED`, `EventType.SESSION_EVALUATION_TRIGGERED`,
`SessionStatus.FAILED`) but never produced. The governance trace is therefore
incomplete: a failed call looks identical to a clean one, and the automatic
evaluation phase leaves no event marker. Closing this gap makes the session
lifecycle observable end to end, which downstream evidence/scoring and any audit
narrative depend on.

## What success looks like

| Outcome | Signal |
|---------|--------|
| Failed sessions are distinguishable | A call ending on an uncontrolled error yields `session.failed` (status `FAILED`), never a silent `session.ended`. |
| Evaluation start is observable | The automatic evaluation entrypoint records exactly one `session.evaluation_triggered` per session. |
| No terminal regression | `end-of-call-report` stays authoritative; a terminal `status-update` still never closes a session. |
| Idempotent | Webhook/task retries never produce duplicate markers or rewrite a closed session's status. |
| Decoupled | No Vapi eval endpoint, no eval run id, no dependency on mock evals. |

## Current state (verified in code)

| Fact | Location |
|------|----------|
| `session.ended` is emitted only from `end-of-call-report` (`source=platform`), regardless of `endedReason`. | `src/adapters/rest/vapi_mapping.py:77` |
| Terminal `status-update` (`ended`/`failed`/`error`) is intentionally raw-only. | `src/adapters/rest/vapi_mapping.py:98` (`_resolve_status_update` maps only `in-progress`) |
| Automatic evaluation = build evidences → evaluate → persist report, enqueued **only** on `SESSION_ENDED`. | `src/adapters/rest/vapi.py:66`, `src/infrastructure/celery/tasks.py:13` |
| `Session.record()` already transitions to `FAILED` on `SESSION_FAILED`, and rejects any event once the session is not `ACTIVE`. | `src/domain/session.py:38,54` |
| `IngestEvent` silently drops any event when the session is already closed. | `src/application/use_cases/ingest_event.py:35` |
| `save_session()` merges the session row (rewrites status/ended_at) and inserts events with `ON CONFLICT (event_id) DO NOTHING` — no `(session_id, event_type)` uniqueness. | `src/infrastructure/repositories/governance_repository.py:64` |
| Migration head is `8e3c03e687de`; a stale compiled-only migration `f1b2c3d4e5f6_add_lifecycle_event_uniqueness` (no `.py`) is left over from the abandoned change. | `alembic/versions/` |

## Approach

Two independent event sources, each aligned with an existing seam.

### `session.failed` — classify the authoritative terminal

Derive it from `end-of-call-report` by inspecting `endedReason`. Error reasons
(e.g. `pipeline-error-*`, `vapifault-*`, `*-error`, unknown/uncontrolled)
resolve to `SESSION_FAILED`; normal hangups keep `SESSION_ENDED`. This is a
**terminal-time, in-band** classification handled by the existing
`Session.record()` `ACTIVE → FAILED` transition — no new domain path needed.

- `session.failed` and `session.ended` are **mutually exclusive**: one terminal
  event per session.
- The "don't lose `end-of-call-report`" fix is preserved because `session.failed`
  is derived **from `end-of-call-report`**, not from `status-update`. Terminal
  `status-update` pings stay raw-only and still cannot pre-empt the report.
- A failed session still carries the report payload, so evidence build stays
  valid. The evaluation enqueue is widened from `SESSION_ENDED` to **any terminal
  event** (`ENDED` or `FAILED`) so failed calls are still evaluated.

### `session.evaluation_triggered` — mark the evaluation entrypoint

Record it at the **start** of `build_session_evidences_async`, before evidences
are built. At that point the session is already terminal (`ENDED`/`FAILED`), so
this is a **post-terminal append** that must bypass the `ACTIVE`-only guard
without rewriting the closed session's status.

- **Domain:** add a dedicated post-terminal append method on `Session` (distinct
  from `record()`), allowed only for the marker event set, that assigns the next
  `sequence_number`, appends the event, and does **not** change `status`/`ended_at`.
- **Application:** a small use case (e.g. `RecordEvaluationTriggered`) invoked by
  the Celery task, depending on the repository port.
- **Repository/port:** a dedicated terminal-marker append that inserts with
  `ON CONFLICT (session_id, event_type) DO NOTHING` and does **not** merge/rewrite
  the session row.

### Idempotency (carried over from the abandoned change — still valid)

- New Alembic migration (branching from `8e3c03e687de`) adds a **partial unique
  index on `(session_id, event_type)`** scoped to the marker event types.
- `ON CONFLICT DO NOTHING` on that index makes repeated evaluation triggers (the
  webhook can fire `end-of-call-report` more than once, each enqueuing the task)
  a no-op after the first.
- `session.failed` terminal idempotency is already covered by the "session
  already closed → return" guard; the partial index also covers it as defense in
  depth.

## Design decisions surfaced (each with a recommendation)

| # | Decision | Options | Recommendation |
|---|----------|---------|----------------|
| 1 | What produces `session.failed`? | (a) `end-of-call-report` with an error `endedReason`; (b) the evaluation Celery task failing; (c) a provider error signal (`status-update`). | **(a).** It matches the canonical definition (the *call* failed), keeps `end-of-call-report` authoritative, is mutually exclusive with `session.ended`, and does not touch the raw-only `status-update` path. (b) conflates pipeline failure with session failure; (c) would regress the terminal-authority fix. |
| 2 | Where is `session.evaluation_triggered` emitted? | Webhook handler vs evaluation task entrypoint. | **Task entrypoint** (`build_session_evidences_async`, at start, session already terminal), so the marker truly reflects the platform's evaluation phase and is written in the evaluation transaction. |
| 3 | How is at-most-one-per-session enforced? | App-level check vs DB partial unique index. | **DB partial unique index on `(session_id, event_type)` + `ON CONFLICT DO NOTHING`**, plus the post-terminal append path that never rewrites a closed session's status. Authoritative under concurrency and webhook/task retries. |
| 4 | Are failed sessions still evaluated? | Yes / no. | **Yes** — widen the enqueue from `SESSION_ENDED` to any terminal event, so a failed call still gets evidences/report and its `evaluation_triggered` marker. |

## Scope

### In scope

- `session.failed` from `end-of-call-report` `endedReason` classification.
- `session.evaluation_triggered` at the evaluation entrypoint, post-terminal.
- Post-terminal append path (domain + port + repository).
- Partial unique index migration on `(session_id, event_type)` for the markers.
- Widening the evaluation enqueue to terminal (`ENDED`/`FAILED`) sessions.
- Test-first coverage for all of the above.

### Out of scope

- Vapi eval endpoints (`POST /eval`, `POST /eval/run`, `GET /eval/run/{id}`) — permanently.
- Any `conversation.*`, `tool.*`, or `system.*` event.
- Changing the raw-only handling of `status-update`.
- Re-scoring/evidence algorithm changes beyond enqueuing on failure.
- Cleaning up the stale `f1b2c3d4e5f6` compiled migration (note it; handle in the failed/index slice if convenient).

## First-slice boundary and delivery

Two independent slices; recommend **chained PRs** (each < 400 lines).

| Slice | Content | Notes |
|-------|---------|-------|
| A — `session.failed` | `endedReason` classification in `vapi_mapping.py`, widen enqueue in `vapi.py`, tests. Uses the existing domain `FAILED` path — no new infra. | Small, self-contained; safe standalone PR. |
| B — `session.evaluation_triggered` | Post-terminal domain method, `RecordEvaluationTriggered` use case, port + repository marker append, task emission, partial-unique-index migration, tests. | Depends on the marker infra; larger. |

A single combined PR would likely exceed the 400-line budget once tests are
included, so chaining is recommended (slice A first).

## Open questions / risks

- Exact `endedReason` taxonomy for "uncontrolled error" vs normal end must be
  pinned in the spec (Vapi documents the set; classification lives in mapping).
- Server currently starts without running migrations (commit `36aa530`); the new
  partial index must be applied out-of-band before slice B relies on it.
- `save_session` rewrites the session row on merge — slice B must use the
  dedicated marker-append path, not `save_session`, to honor "never rewrite a
  closed session's status".
- Strict TDD is active: every behavior lands as a failing test first.
