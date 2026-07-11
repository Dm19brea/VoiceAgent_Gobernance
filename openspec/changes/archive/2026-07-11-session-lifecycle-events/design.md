# Technical Design — Session Lifecycle Events

Emit the two remaining canonical `session.*` events from the platform, fully
decoupled from Vapi eval. `session.failed` is an in-band terminal classification
of `end-of-call-report`; `session.evaluation_triggered` is a post-terminal marker
appended at the start of the evaluation task. Idempotency is enforced by a DB
partial unique index on `(session_id, event_type)`.

## Architecture at a glance

| Concern | Seam (existing) | What we add |
|---------|-----------------|-------------|
| Classify `session.failed` | `vapi_mapping._resolve` (end-of-call-report → `SESSION_ENDED`) | pure `classify_terminal_event(ended_reason)` selecting `SESSION_FAILED` vs `SESSION_ENDED` |
| Close the session as FAILED | `Session.record()` ACTIVE→FAILED (already exists) | nothing new — reuse the existing `SESSION_FAILED` branch |
| Evaluate failed sessions | `vapi.py` enqueue guard | widen `SESSION_ENDED` → any terminal (`ENDED`/`FAILED`) |
| Live store cleanup | `active_sessions.update_active_state` | widen `mark_ended` to fire on `FAILED` too |
| Mark evaluation start | `tasks.build_session_evidences_async` | `RecordEvaluationTriggered` use case + `Session.append_marker()` |
| Persist marker without rewriting the closed row | `governance_repository` | `append_marker_event()` with `ON CONFLICT DO NOTHING` |
| At-most-one marker per session | DB schema | partial unique index migration from `8e3c03e687de` |

No new configuration: the feature is decoupled, so `src/infrastructure/config.py`
is untouched (confirmed — no outbound eval URL, no run id).

Data flow (two independent paths):

```
Slice A (terminal classification, synchronous, in the webhook request):
  Vapi end-of-call-report
    -> map_vapi_event -> _resolve -> classify_terminal_event(endedReason)
       -> SESSION_ENDED | SESSION_FAILED
    -> IngestEvent.execute -> Session.record() [ACTIVE -> ENDED|FAILED]
    -> save_session (merge row + events)
    -> commit
    -> if terminal (ENDED|FAILED): build_session_evidences.delay(call_id)
    -> update_active_state -> mark_ended on ENDED|FAILED

Slice B (evaluation marker, asynchronous, in the Celery task):
  build_session_evidences_async(session_id)
    -> get_session (already ENDED|FAILED)
    -> RecordEvaluationTriggered.execute(session)
         -> Session.append_marker(SESSION_EVALUATION_TRIGGERED)  [status unchanged]
         -> repo.append_marker_event(event)  [ON CONFLICT (session_id,event_type) DO NOTHING]
    -> commit (marker durable)
    -> build_evidences -> add_evidences -> add_report -> commit
```

## 1. endedReason classifier

**Placement:** a pure module-level function in `src/adapters/rest/vapi_mapping.py`,
next to `_normalise_report`. Classification is a mapping concern (provider
vocabulary → canonical event), so it stays out of the domain.

```python
_FAILURE_SUBSTRINGS = ("error", "fault")
_FAILURE_PREFIXES = (
    "pipeline-",
    "call.start.error-",
    "call.in-progress.error-",
    "call-start-error-",
)
_FAILURE_REASONS = frozenset({
    "llm-failed",
    "pipeline-no-available-llm-model",
    "phone-call-provider-closed-websocket",
    "worker-shutdown",
    "assistant-not-found",
    "assistant-not-valid",
    "assistant-request-failed",
    "assistant-join-timed-out",
})
_FAILURE_CONTAINS = (
    "-voice-failed",
    "-transcriber-failed",
    "-transport-",
    "-worker-",
)
_FAILURE_PREFIXES_FAMILY = ("twilio-", "vonage-", "assistant-request-returned-")


def classify_terminal_event(ended_reason: object) -> EventType:
    """Map a Vapi ``endedReason`` to the canonical terminal event.

    Fail-safe: only a recognised error signal yields ``SESSION_FAILED``; every
    other value — including ``None`` and unknown reasons — defaults to
    ``SESSION_ENDED`` (absence of a known failure is treated as a normal end).
    """
    if not isinstance(ended_reason, str):
        return EventType.SESSION_ENDED
    reason = ended_reason.strip().lower()
    if not reason:
        return EventType.SESSION_ENDED
    if reason in _FAILURE_REASONS:
        return EventType.SESSION_FAILED
    if any(s in reason for s in _FAILURE_SUBSTRINGS):
        return EventType.SESSION_FAILED
    if any(s in reason for s in _FAILURE_CONTAINS):
        return EventType.SESSION_FAILED
    if reason.startswith(_FAILURE_PREFIXES) or reason.startswith(_FAILURE_PREFIXES_FAMILY):
        return EventType.SESSION_FAILED
    return EventType.SESSION_ENDED
```

**How it selects the event while keeping the payload/report:** `_resolve` currently
returns `(SESSION_ENDED, PLATFORM)` for `end-of-call-report` unconditionally
(line 77-78). Change only that branch to consult the classifier:

```python
if vapi_type == "end-of-call-report":
    return (classify_terminal_event(message.get("endedReason")), Source.PLATFORM)
```

The payload assembly in `map_vapi_event` (lines 49-51) is unchanged: `payload`
still carries the full `message` plus `report = _normalise_report(...)`, which
already exposes `ended_reason`. So a `session.failed` event carries the ended
reason and normalised report fields with zero extra work — satisfying the
"payload carries the ended reason" scenario. The event type is the only thing
that diverges; the report survives on both branches.

**Fail-safe default:** any reason not matched (including `None` / unknown) returns
`SESSION_ENDED`. This directly implements the spec's "unknown reason defaults to
normal end" scenario and the "absence of a known error signal is a normal end"
rule.

**Rationale / rejected alternatives:**
- *Rejected:* deriving `session.failed` from terminal `status-update`. That would
  regress the terminal-authority fix (`_resolve_status_update` stays raw-only,
  mapping only `in-progress`). `status-update` is untouched.
- *Rejected:* a whitelist of "normal" reasons with everything else = failure.
  That is fail-*open* (any new Vapi reason silently fails good calls). We chose
  fail-*closed-to-normal*: only known error signals fail, matching the spec.
- *Substring `error`/`fault` + prefix families* over an exhaustive literal set:
  Vapi's taxonomy evolves; pattern matching absorbs new `pipeline-error-*` /
  `vapifault-*` variants without a code change while the explicit set/`_CONTAINS`
  tuple pins the non-obvious named failures the spec enumerates.

## 2. Domain post-terminal append

Add a second, purpose-built method on `Session` — distinct from `record()` — so
the ACTIVE-only invariant of `record()` is never weakened.

```python
_MARKER_EVENTS = frozenset({EventType.SESSION_EVALUATION_TRIGGERED})

def append_marker(
    self,
    event_type: EventType,
    source: Source,
    timestamp: datetime,
    payload: dict[str, Any],
) -> Event:
    """Append a post-terminal marker without changing lifecycle state.

    Allowed only for marker events on an already-terminal session. Assigns the
    next sequence number and appends the event, but never touches ``status`` or
    ``ended_at`` — the session stays ENDED/FAILED.
    """
    if event_type not in _MARKER_EVENTS:
        raise DomainError(f"{event_type} is not a post-terminal marker")
    if self.status is SessionStatus.ACTIVE:
        raise SessionClosedError(
            f"Session {self.session_id} is still ACTIVE; markers are post-terminal"
        )
    event = Event(
        session_id=self.session_id,
        event_type=event_type,
        source=source,
        sequence_number=len(self.events) + 1,
        timestamp=timestamp,
        payload=payload,
    )
    self.events.append(event)
    return event
```

**Invariants:**
- Assigns `len(self.events) + 1`, continuing the session's existing sequence
  (satisfies the schema requirement "sequence_number continuing the session's
  sequence").
- Allowed only for the marker set (`SESSION_EVALUATION_TRIGGERED`). `session.failed`
  is deliberately NOT in this set — it is emitted in-band via `record()`.
- Does NOT mutate `status` / `ended_at` — the closed session stays closed.
- Rejects an ACTIVE session: markers are, by definition, post-terminal.

**Coexistence with `record()`'s ACTIVE-only guard:** the two methods are
complementary and mutually exclusive by state.
- `record()` requires ACTIVE and *drives* transitions (including ACTIVE→FAILED).
  Its guard is unchanged; it still rejects everything once closed.
- `append_marker()` requires NON-ACTIVE and never transitions.
There is no path where a marker reopens or rewrites a session, and no path where
`record()` handles a post-terminal event. The reused `SessionClosedError` (from a
mis-timed marker on an ACTIVE session) is a genuine programming error, not a Vapi
edge — the task only runs post-terminal.

## 3. Application — RecordEvaluationTriggered use case + port method

**Use case** `src/application/use_cases/record_evaluation_triggered.py`. It accepts
the already-loaded `Session` (the task loads it anyway) to avoid a redundant query:

```python
class RecordEvaluationTriggered:
    """Append the platform's evaluation-start marker to a terminal session."""

    def __init__(self, repository: GovernanceRepository) -> None:
        self._repo = repository

    async def execute(self, session: Session, timestamp: datetime) -> None:
        event = session.append_marker(
            EventType.SESSION_EVALUATION_TRIGGERED,
            Source.PLATFORM,
            timestamp,
            payload={},
        )
        await self._repo.append_marker_event(event)
```

`payload={}` is allowed by the schema requirement ("MAY be empty ... no report
duplication required"). `source = platform` per spec.

**Port method** added to `GovernanceRepository` (Protocol):

```python
async def append_marker_event(self, event: Event) -> None: ...
```

It persists a single event row idempotently and MUST NOT rewrite the session
row. Distinct from `save_session` precisely because `save_session` merges (and
therefore rewrites) the `SessionModel`.

**Rationale / rejected alternatives:**
- *Rejected:* reuse `save_session`. It calls `session.merge(_to_session_model(...))`,
  which would rewrite `status`/`ended_at` of the closed session and (worse) could
  overwrite a concurrently-updated row. The whole point of the marker path is to
  touch only the events table.
- *Passing the domain `Event`* (not the whole `Session`) to the port keeps the
  repository's responsibility narrow: append one row, honour the unique index.

## 4. Repository — idempotent marker append

`SqlAlchemyGovernanceRepository.append_marker_event`:

```python
async def append_marker_event(self, event: Event) -> None:
    stmt = (
        pg_insert(EventModel)
        .values(**_event_values(event))
        .on_conflict_do_nothing(
            index_elements=["session_id", "event_type"],
            index_where=EventModel.event_type.in_(
                [
                    EventType.SESSION_EVALUATION_TRIGGERED.value,
                    EventType.SESSION_FAILED.value,
                ]
            ),
        )
    )
    await self._session.execute(stmt)
```

Key points:
- **No `save_session`, no `merge`.** Only the events table is written; the closed
  session row is never rewritten — honouring "never rewrite a closed session's
  status".
- **Partial-index conflict inference.** Postgres requires the `ON CONFLICT`
  inference to match a *partial* unique index, so `index_where` MUST reproduce the
  index predicate (the two marker event types). Omitting `index_where` would raise
  `there is no unique or exclusion constraint matching the ON CONFLICT
  specification`. This is the single most error-prone detail of Slice B.
- Reuses the existing `_event_values` helper (no schema drift).
- Idempotent under retries: a redelivered task is a no-op after the first insert.

## 5. Migration — partial unique index

New revision under `backend/alembic/versions/`, `down_revision = "8e3c03e687de"`
(current head; the stale `f1b2c3d4e5f6` orphan has been removed):

```python
revision = "<new_hash>_add_session_marker_uniqueness"
down_revision = "8e3c03e687de"

_MARKER_TYPES = ("session.evaluation_triggered", "session.failed")

def upgrade() -> None:
    op.create_index(
        "uq_events_session_marker",
        "events",
        ["session_id", "event_type"],
        unique=True,
        postgresql_where=sa.text(
            "event_type IN ('session.evaluation_triggered', 'session.failed')"
        ),
    )

def downgrade() -> None:
    op.drop_index("uq_events_session_marker", table_name="events")
```

- **Partial** (scoped to the two marker types) so it never constrains the many
  legitimate repeated events (e.g. multiple `conversation.*`, `tool.called`).
- The predicate string MUST exactly match the `index_where` used in
  `append_marker_event` for conflict inference to bind.
- The ORM `EventModel` needs no column change; the index is DB-only. (Optionally
  mirror it in `models.py` via `__table_args__` for autogenerate parity, but the
  migration is authoritative.)

**Out-of-band application caveat (commit `36aa530`):** the server now starts
*without* running migrations. This index is a hard dependency of Slice B's
idempotency, so it MUST be applied out-of-band (`alembic upgrade head` against the
target DB) **before** Slice B is deployed. If the index is missing, the `ON
CONFLICT` insert raises — Slice B's PR notes and deploy runbook must call this
out explicitly. Slice A does not depend on the index (terminal idempotency is
already covered by the closed-session guard).

## 6. Enqueue widening

In `src/adapters/rest/vapi.py` (line 66), widen the terminal guard so failed
sessions are still evaluated:

```python
_TERMINAL_EVENTS = (EventType.SESSION_ENDED, EventType.SESSION_FAILED)
...
if command is not None and command.event_type in _TERMINAL_EVENTS:
    try:
        build_session_evidences.delay(command.call_id)
    except Exception:
        logger.exception("Failed to enqueue evidence build: session={}", command.call_id)
```

**Companion fix (same slice):** `active_sessions.update_active_state` (line 68)
only calls `mark_ended` on `SESSION_ENDED`. A `FAILED` session would otherwise
leak in the live active-session store forever. Widen it to the terminal set:

```python
elif command.event_type in (EventType.SESSION_ENDED, EventType.SESSION_FAILED):
    await store.mark_ended(command.call_id)
```

This is discovered-in-code and belongs to Slice A (it is part of "a failed call
must behave like a terminal call end-to-end").

## 7. Failure-closed behaviour + observability

The spec's failure-closed requirement is *cross-session isolation*: one session's
classification/append error must not block ingestion of other sessions' events.

- **Classification (Slice A):** `classify_terminal_event` is total and pure — it
  cannot raise on arbitrary input (non-str/None → `SESSION_ENDED`). There is no
  failure mode to isolate; the webhook path is unchanged otherwise.
- **Marker append (Slice B):** each Celery task runs in its own engine/session
  (`create_async_engine(..., NullPool)` per run), so a marker failure is already
  isolated to that one task/session — it cannot affect other sessions'
  ingestion. Satisfies "a classification error does not break other sessions".
- **Marker durability vs evidence outcome (decision):** commit the marker in its
  own transaction *before* building evidences:

  ```python
  repository = SqlAlchemyGovernanceRepository(session)
  governance_session = await repository.get_session(session_id)
  if governance_session is None:
      return 0
  await RecordEvaluationTriggered(repository).execute(governance_session, datetime.now(UTC))
  await session.commit()   # marker durable regardless of evidence outcome
  evidences = build_evidences(governance_session)
  ...
  await session.commit()
  ```

  *Rationale:* the marker records that evaluation *started*; it should survive an
  evidence/scoring failure so the governance trace reflects the attempt. `ON
  CONFLICT DO NOTHING` keeps the retry a no-op. *Rejected:* a single end-of-task
  commit — it couples the marker's durability to evidence success and loses the
  "evaluation started" signal on failure.

- **Observability:** log at INFO on marker insert (`session.evaluation_triggered
  recorded: session={}`) and at INFO when classification yields `session.failed`
  (`end-of-call-report classified as session.failed: session={} reason={}`), so
  failed calls and evaluation starts are greppable. Marker-append exceptions
  propagate to Celery (task marked failed → retried), which is acceptable given
  idempotency; they are not swallowed silently.

## 8. Delivery — 2 chained PRs

Confirmed: two independent slices, chained, each under the 400-line budget.

| Slice / PR | Scope | Depends on | Migration? |
|-----------|-------|------------|------------|
| **PR-1 — Slice A: `session.failed`** | `classify_terminal_event` + wire into `_resolve`; widen enqueue in `vapi.py`; widen `mark_ended` in `active_sessions.py`; tests. Reuses existing `record()` FAILED path — no new infra, no migration. | proposal/spec only | No |
| **PR-2 — Slice B: `session.evaluation_triggered`** | `Session.append_marker`; `RecordEvaluationTriggered`; port `append_marker_event`; repo impl; task emission + own-transaction commit; partial-index migration; coverage-doc update; tests. | PR-1 merged; index applied out-of-band | Yes (out-of-band) |

**PR-1 boundary (clear cut):** everything needed to distinguish a failed call —
classification, evaluation enqueue on failure, and live-store cleanup on failure —
with tests. It is safe to ship standalone: it changes only which terminal event
type is produced and reuses the already-existing domain FAILED transition. No
schema change, no new module wiring, so no deploy-ordering constraint.

**PR-2 boundary:** all marker infrastructure. Its only cross-cutting risk is the
out-of-band index, called out in the PR description and runbook.

Strict TDD: every behaviour above lands as a failing test first (classifier
table cases, mutual-exclusivity, marker post-terminal append, ON CONFLICT no-op,
enqueue-on-failure, active-store cleanup-on-failure).

## Decisions (ADR-style summary)

| # | Decision | Chosen | Rejected | Why |
|---|----------|--------|----------|-----|
| D1 | Source of `session.failed` | classify `end-of-call-report` `endedReason` | task failure; `status-update` | keeps report authoritative, mutually exclusive with `ended`, no terminal-authority regression |
| D2 | Classifier default | fail-safe → `session.ended` | fail-open → `session.failed` | unknown reasons are normal ends per spec; avoids failing good calls on new Vapi vocab |
| D3 | Marker append path | new `append_marker()` + `append_marker_event()` | reuse `record()` / `save_session` | must not weaken ACTIVE-only guard nor rewrite the closed session row |
| D4 | At-most-one enforcement | DB partial unique index + `ON CONFLICT DO NOTHING` | app-level check | authoritative under concurrency and webhook/task retries |
| D5 | Marker transaction | own commit before evidences | single end-of-task commit | marker survives evidence/scoring failure; retry stays a no-op |
| D6 | Evaluate failed sessions | widen enqueue to terminal set | keep `ENDED`-only | failed calls still get evidences/report and their marker |
| D7 | Delivery | 2 chained PRs (A then B) | single PR | combined diff exceeds 400 lines with tests; A is safely standalone |
```
