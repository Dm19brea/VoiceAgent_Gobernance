# Live Speaking Indicator Specification

## Purpose

Give the live monitoring view a real-time signal of who is currently speaking
(agent or user) and when the user interrupted the agent, sourced from Vapi's
`speech-update` and `user-interrupted` webhooks. `conversation-update` is never
used for this signal. `turn_started`/`turn_ended` remain live-only and are not
persisted as canonical events.

## Requirements

### Requirement: Agent speaking state reflected live

The system MUST set `speaking_role` to `agent` on the active-session snapshot
when a `conversation.turn_started` event with `source: agent` is ingested for
that session, and MUST clear it to `null` when the matching
`conversation.turn_ended` event with `source: agent` arrives.

#### Scenario: Agent starts speaking

- GIVEN an active session with `speaking_role: null`
- WHEN a `speech-update` webhook `{role: assistant, status: started}` is ingested
- THEN the session's snapshot `speaking_role` becomes `agent`
- AND the change is visible on the next WebSocket push

#### Scenario: Agent stops speaking

- GIVEN an active session with `speaking_role: agent`
- WHEN a `speech-update` webhook `{role: assistant, status: stopped}` is ingested
- THEN the session's snapshot `speaking_role` becomes `null`

### Requirement: User speaking state reflected live

The system MUST set `speaking_role` to `user` when a `conversation.turn_started`
event with `source: user` is ingested, and MUST clear it to `null` when the
matching `conversation.turn_ended` event with `source: user` arrives.

#### Scenario: User starts speaking

- GIVEN an active session with `speaking_role: null`
- WHEN a `speech-update` webhook `{role: user, status: started}` is ingested
- THEN the session's snapshot `speaking_role` becomes `user`

#### Scenario: User stops speaking

- GIVEN an active session with `speaking_role: user`
- WHEN a `speech-update` webhook `{role: user, status: stopped}` is ingested
- THEN the session's snapshot `speaking_role` becomes `null`

### Requirement: User interruption surfaced live

The system MUST stamp `last_interruption_at` on the active-session snapshot
with the event timestamp when a `conversation.interruption_detected` event
(from `user-interrupted`) is ingested for that session, without altering
`speaking_role` as a side effect of the interruption itself.

#### Scenario: User interrupts the agent

- GIVEN an active session while the agent is speaking (`speaking_role: agent`)
- WHEN a `user-interrupted` webhook is ingested for that session
- THEN the session's snapshot `last_interruption_at` is set to the event timestamp
- AND the live view can render an interruption indicator from this field

### Requirement: Speaking state cleared on session end

The system MUST reset `speaking_role` to `null` and MUST leave
`last_interruption_at` unset (or cleared) when a session ends, so no stale
speaking indicator survives session termination.

#### Scenario: Session ends while agent or user was mid-turn

- GIVEN an active session with `speaking_role: agent` (or `user`)
- WHEN a `SESSION_ENDED` or `SESSION_FAILED` event is ingested for that session
- THEN the session snapshot is removed (or marked ended) with `speaking_role: null`
- AND no further speaking indicator is shown for that session

### Requirement: Missing turn_ended does not permanently stick

The system SHOULD treat `speaking_role` as a best-effort live hint, not an
authoritative lock: a dropped/missing `turn_ended` for a session MUST NOT
prevent that session's speaking indicator from clearing once the session ends
or a subsequent `turn_started` for a different role arrives.

#### Scenario: turn_ended never arrives, then the other role starts speaking

- GIVEN an active session with `speaking_role: agent` and no `turn_ended` was received
- WHEN a `speech-update` `{role: user, status: started}` is ingested
- THEN the session's snapshot `speaking_role` becomes `user` (overwritten, not blocked)

#### Scenario: turn_ended never arrives, then the session ends

- GIVEN an active session with `speaking_role: agent` and no `turn_ended` was received
- WHEN the session ends (`SESSION_ENDED`/`SESSION_FAILED`)
- THEN `speaking_role` is cleared per the session-end requirement above

### Requirement: New snapshot fields are backward-compatible

The system MUST default `speaking_role` to `null` and `last_interruption_at`
to `null` for snapshots that predate this change or that never receive a
`speech-update`/`user-interrupted` event, so existing consumers of the
active-session snapshot and WebSocket stream do not break.

#### Scenario: Session with no speech-update traffic yet

- GIVEN a session just started via `SESSION_STARTED`
- WHEN no `speech-update` or `user-interrupted` has been ingested yet
- THEN the snapshot reports `speaking_role: null` and `last_interruption_at: null`

### Requirement: Live-only, no canonical persistence expansion

`turn_started`/`turn_ended` speaking-state updates MUST remain a live-only
projection onto the active-session snapshot. This change MUST NOT add
canonical persistence, taxonomy changes, or `conversation-update` usage.

#### Scenario: Raw landing and canonical events unaffected

- GIVEN a `speech-update` webhook is received
- WHEN it is landed raw and mapped to a canonical turn event as today
- THEN no new canonical event types or persisted rows are introduced by this change
- AND the only new effect is the active-session snapshot update and WebSocket serialization
