# Session Lifecycle Events Specification

## Purpose

Define the platform-emitted terminal and evaluation-marker events (`session.failed`,
`session.evaluation_triggered`) that close the canonical `session.*` event
taxonomy, fully decoupled from Vapi's mock-conversation eval feature.

## Requirements

### Requirement: Terminal event classification from end-of-call-report

The system MUST classify every `end-of-call-report` webhook into exactly one
terminal event — `session.ended` (normal) or `session.failed` (uncontrolled
error) — based on the Vapi `endedReason` field. The system MUST NOT classify a
terminal `status-update` as either event; that path stays raw-only.

Classification rule: `endedReason` maps to `session.failed` when it matches an
error signal — contains `error` or `vapifault` (not bare `fault`, to avoid
false positives on unrelated words such as "default"), or starts with
`pipeline-`, `call.start.error-`, `call.in-progress.error-`,
`call-start-error-`, or names a known failure (`llm-failed`, `*-voice-failed`,
`*-transcriber-failed`, `pipeline-no-available-llm-model`,
`phone-call-provider-closed-websocket`, `twilio-*`, `vonage-*`,
`*-transport-*`, `*-worker-*`, `worker-shutdown`, `assistant-not-found`,
`assistant-not-valid`, `assistant-request-failed`, `assistant-join-timed-out`,
`assistant-request-returned-*`). Every other `endedReason`, including
unrecognized/unknown values, MUST map to `session.ended` (fail-safe default:
absence of a known error signal is treated as a normal end, not a failure).

#### Scenario: Normal hangup ends the session

- GIVEN an active session
- WHEN `end-of-call-report` arrives with `endedReason = "customer-ended-call"`
- THEN the system emits `session.ended` and the session status becomes `ENDED`

#### Scenario: Error reason fails the session

- GIVEN an active session
- WHEN `end-of-call-report` arrives with `endedReason = "pipeline-error-openai-llm-failed"`
- THEN the system emits `session.failed` and the session status becomes `FAILED`

#### Scenario: Transport/provider error fails the session

- GIVEN an active session
- WHEN `end-of-call-report` arrives with `endedReason = "twilio-failed-to-connect-call"`
- THEN the system emits `session.failed` and the session status becomes `FAILED`

#### Scenario: Unknown reason defaults to normal end

- GIVEN an active session
- WHEN `end-of-call-report` arrives with an `endedReason` not present in the
  documented Vapi taxonomy
- THEN the system emits `session.ended`, not `session.failed`

### Requirement: Mutual exclusivity of terminal events

The system MUST emit exactly one terminal event (`session.ended` XOR
`session.failed`) per session. A session that has already recorded one
terminal event MUST reject further terminal events.

#### Scenario: Second terminal event is rejected

- GIVEN a session already `ENDED` from a prior `end-of-call-report`
- WHEN a second `end-of-call-report` arrives for the same session
- THEN the system does not emit a new terminal event and the session status
  remains `ENDED`

### Requirement: Terminal status-update never closes a session

A terminal `status-update` (`ended`, `failed`, `error`) MUST remain raw-only
and MUST NOT emit `session.ended` or `session.failed` or change session
status. Only `end-of-call-report` is authoritative for terminal classification.

#### Scenario: Terminal status-update does not close the session

- GIVEN an active session
- WHEN a `status-update` webhook arrives with `status = "ended"`
- THEN no `session.ended` or `session.failed` event is emitted and the session
  remains `ACTIVE`

### Requirement: Evaluation-triggered marker at task start

The system MUST emit exactly one `session.evaluation_triggered` event per
session, recorded at the start of the automatic-evaluation task
(`build_session_evidences_async`), before evidence building begins. This event
MUST be appended post-terminal (session already `ENDED` or `FAILED`) and MUST
NOT change the session's `status` or `ended_at`.

#### Scenario: Evaluation start is recorded for an ended session

- GIVEN a session with status `ENDED`
- WHEN the automatic evaluation task starts for that session
- THEN the system appends `session.evaluation_triggered` and the session
  status remains `ENDED`

#### Scenario: Evaluation start is recorded for a failed session

- GIVEN a session with status `FAILED`
- WHEN the automatic evaluation task starts for that session
- THEN the system appends `session.evaluation_triggered` and the session
  status remains `FAILED`

### Requirement: Failed sessions are still evaluated

The evaluation enqueue MUST trigger on any terminal event (`session.ended` OR
`session.failed`), not only on `session.ended`.

#### Scenario: A failed session is enqueued for evaluation

- GIVEN a session terminates with `session.failed`
- WHEN the terminal event is processed
- THEN the automatic-evaluation task is enqueued for that session

### Requirement: Terminal-derived evidence and scoring treat session.failed the same as session.ended for duration and reason, but distinctly for completion

The evidence builder and the metric catalogue MUST treat `session.failed` as a
terminal event on par with `session.ended` for the `session_duration_seconds`
evidence's `source_events` and the `ended_reason` evidence: both MUST be
produced for a session whose trace ends in `session.failed`, using that
event's end-of-call report payload.

For the completion criterion, `session.failed` and `session.ended` MUST be
treated distinctly, not on par: a session terminating in `session.ended` MUST
yield a `session_completed` evidence (conclusion "The session completed"); a
session terminating in `session.failed` MUST instead yield a distinct
`session_failed` evidence (conclusion "The session failed") and MUST NOT
yield a `session_completed` evidence. Consequently:

- The blocking-flag detector MUST raise `FLAG_SESSION_FAILED` (a blocking
  flag) when a `session_failed` evidence is present, and MUST raise
  `FLAG_SESSION_NOT_COMPLETED` only when NEITHER `session_completed` NOR
  `session_failed` evidence is present.
- The metric catalogue's `completion` metric MUST be gated on the
  `session_completed` criterion only, so it is absent (never faked) for a
  failed session, while the `clean_ending` risk metric MUST still be computed
  from the terminal event's report regardless of outcome.

#### Scenario: Ended-reason evidence is produced for a failed session

- GIVEN a session terminates with `session.failed` and an end-of-call report
  carrying `ended_reason = "pipeline-error-openai-llm-failed"`
- WHEN evidences are built for that session
- THEN an `ended_reason` evidence is produced with that reason, and the
  `session_duration_seconds` evidence's `source_events` includes the
  `session.failed` event id

#### Scenario: Clean-ending metric is computed and zero for a failed session

- GIVEN a session terminates with `session.failed` and an end-of-call report
  carrying an error `ended_reason`
- WHEN metrics are computed for that session
- THEN a `clean_ending` metric is present with `raw_value = 0.0`

#### Scenario: Failed session raises the session-failed blocking flag and no completion credit

- GIVEN a session terminates with `session.failed`
- WHEN evidences are built and the session is evaluated
- THEN a `session_failed` evidence is produced (not `session_completed`), the
  evaluator raises exactly the `FLAG_SESSION_FAILED` blocking flag (not
  `FLAG_SESSION_NOT_COMPLETED`), no `completion` metric is present, and the
  session's final result is `FAILED`

### Requirement: Idempotent marker events

The system MUST persist at most one `session.evaluation_triggered` and at most
one `session.failed` per session, enforced by a database partial unique
constraint on `(session_id, event_type)` for these marker types, combined with
an insert that is a no-op on conflict.

#### Scenario: Duplicate end-of-call-report does not duplicate session.failed

- GIVEN a session already `FAILED` from a prior `end-of-call-report`
- WHEN the same `end-of-call-report` webhook is redelivered
- THEN no second `session.failed` event is persisted

#### Scenario: Evaluation task retry does not duplicate the marker

- GIVEN `session.evaluation_triggered` was already recorded for a session
- WHEN `build_session_evidences_async` is retried for the same session
- THEN no second `session.evaluation_triggered` event is persisted

### Requirement: Event schema

Every emitted `session.failed` or `session.evaluation_triggered` event MUST
carry: `event_type`, `session_id`, `agent_id`, a `sequence_number` continuing
the session's existing sequence, a `timestamp`, `source = platform`, and a
`payload`. For `session.failed`, `payload` MUST include the `endedReason` and
the normalised end-of-call report fields. For `session.evaluation_triggered`,
`payload` MAY be empty or MUST include only evaluation-context fields (no
report duplication required).

#### Scenario: session.failed payload carries the ended reason

- GIVEN an `end-of-call-report` with `endedReason = "pipeline-error-transcriber-failed"`
- WHEN the system emits `session.failed`
- THEN the event payload includes `ended_reason = "pipeline-error-transcriber-failed"`

### Requirement: Failure-closed event processing

An error while classifying `endedReason` or while appending the
evaluation-triggered marker MUST NOT prevent ingestion of other unrelated
events for other sessions.

#### Scenario: A classification error does not break other sessions

- GIVEN classification of one session's `end-of-call-report` raises an error
- WHEN another session's webhook is processed concurrently
- THEN the other session's event is ingested normally

### Requirement: Event coverage documentation stays current

The event-coverage reference documentation MUST be updated to reflect
`session.failed` and `session.evaluation_triggered` as implemented (not
pending) once this change lands.

#### Scenario: Coverage doc reflects the new events

- GIVEN `docs/design/vapi-event-coverage.md` rows for `session.failed` and
  `session.evaluation_triggered`
- WHEN this change is applied
- THEN both rows are updated to state the events are implemented and cite
  their emission points
