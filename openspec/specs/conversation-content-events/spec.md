# Conversation Content Events Specification

## Purpose

Define post-terminal derivation of `conversation.agent_response` and
`conversation.user_input` canonical events from the `end-of-call-report`
webhook's `message.artifact.messagesOpenAIFormatted`, replacing the dead
`conversation-update` mapping path.

## Requirements

### Requirement: Content events derived from end-of-call-report

The system MUST derive one `conversation.agent_response` event per
`messagesOpenAIFormatted` entry with `role="assistant"` and one
`conversation.user_input` event per entry with `role="user"`, in the same
order they appear in the report, appended post-terminal in
`build_session_evidences_async` (after `session.evaluation_triggered`).

#### Scenario: Report with N messages produces N ordered content events

- GIVEN an `end-of-call-report` whose `messagesOpenAIFormatted` contains N
  entries alternating `user`/`assistant` roles
- WHEN the post-terminal evidence build runs for that session
- THEN N content events are appended (assistant entries as
  `conversation.agent_response`, user entries as `conversation.user_input`)
- AND their relative order matches the conversation order in the report

#### Scenario: System role entries are ignored

- GIVEN a `messagesOpenAIFormatted` entry with `role="system"`
- WHEN content events are derived
- THEN no event is created for that entry

#### Scenario: Empty or missing messagesOpenAIFormatted is a no-op

- GIVEN an `end-of-call-report` with an empty or absent
  `messagesOpenAIFormatted` array
- WHEN the post-terminal evidence build runs
- THEN zero content events are appended
- AND the build does not raise an error
- AND the raw report is still retained as landing data

### Requirement: Field semantics — provenance sequence, chronological timestamp

Each content event's `sequence_number` MUST reflect ingestion/provenance
order (monotonic, collision-free per session, assigned as
`len(events) + 1`). Each content event's `timestamp` MUST reflect the true
chronological time of that turn, sourced from the report's
`messages[].time` for the matching turn.

#### Scenario: Content events land after in-call events by sequence

- GIVEN a session whose events already include in-call events and
  `session.ended`/`session.failed`
- WHEN content events are appended post-terminal
- THEN each content event receives the next available `sequence_number`
  (after all existing events, including terminal and
  `session.evaluation_triggered`)
- AND consumers reconstructing the real timeline order by `timestamp`, not
  by `sequence_number`

#### Scenario: Timestamp reflects the turn's real time

- GIVEN a report entry whose corresponding `messages[]` record has
  `time = T`
- WHEN the matching content event is created
- THEN its `timestamp` equals `T` (not the report receipt time)

### Requirement: Post-terminal append does not mutate session lifecycle

Appending content events MUST be valid only once the session is no longer
ACTIVE (ENDED or FAILED), and MUST NOT change `status` or `ended_at`,
analogous to `append_marker` / `append_system_observation`.

#### Scenario: Content events append to an already-terminal session

- GIVEN a session already in ENDED or FAILED status
- WHEN content events are appended
- THEN the append succeeds
- AND `status` and `ended_at` remain unchanged

### Requirement: Retry-safe idempotent identity

Each content event's identity MUST be a UUID5 fingerprint derived from
stable canonical fields — `session_id`, `event_type`, `role`, normalized
turn content, and turn index — explicitly excluding timestamps and raw
delivery/provenance identifiers. Re-processing the same report, or a Vapi
webhook redelivery, MUST NOT create duplicate content events.

#### Scenario: Reprocessing the same report is idempotent

- GIVEN content events were already derived and persisted for a session
- WHEN the same `end-of-call-report` is processed again for that session
  (e.g. re-run of the post-terminal build)
- THEN no new content events are created for the already-seen turns
- AND the existing events are returned/left unchanged

#### Scenario: Vapi redelivers the end-of-call-report webhook

- GIVEN a session whose content events were already derived
- WHEN Vapi redelivers the same `end-of-call-report` webhook (duplicate
  delivery, different raw delivery id)
- THEN the derived content events resolve to the same UUID5 identities
- AND no duplicate rows are persisted

### Requirement: conversation-update is landing-only

`conversation-update` MUST NOT be routed to `_resolve_role_message` or any
other canonical-event mapping. It MUST be retained only as raw landing
data.

#### Scenario: conversation-update webhook produces no canonical event

- GIVEN a `conversation-update` webhook payload is received
- WHEN the event is processed
- THEN the raw payload is landed
- AND no `conversation.*` (or any other) canonical event is created from it
