# Conversation Signal Events Specification

## Purpose

Define a post-terminal LLM-judge step over the full call transcript that
emits canonical governance signals — topic-change count and a
mutually-exclusive goal verdict — reusing the existing idempotent
post-terminal pipeline, with failure isolation from content derivation.

## Requirements

### Requirement: Judge runs post-terminal over the full transcript

The system MUST run an LLM judge over the full transcript (built from the
same `artifact.messagesOpenAIFormatted` used by `derive_conversation_content`)
after `_record_conversation_content` completes in
`build_session_evidences_async`, triggered by the `end-of-call-report`
webhook. The judge MUST NOT run live/in-call.

#### Scenario: Judge runs after content derivation on end-of-call-report

- GIVEN an `end-of-call-report` webhook has been processed and content
  events derived
- WHEN the post-terminal evidence build continues
- THEN the judge step runs against the full transcript for that session
- AND it executes only after `_record_conversation_content` completes

### Requirement: Judge emits at most one topic_change event per call

The system MUST emit exactly one `conversation.topic_change` event per call
when the judge detects at least one topic shift, with payload `count`
(number of topic changes) and `topics` (ordered list). The system MUST NOT
emit one event per detected topic shift.

#### Scenario: Call with multiple topic shifts yields one aggregated event

- GIVEN a transcript in which the judge detects 3 topic shifts
- WHEN the judge completes successfully
- THEN exactly one `conversation.topic_change` event is appended with
  `count = 3` and `topics` listing the shifts in order

### Requirement: Judge emits exactly one mutually-exclusive goal verdict

The system MUST emit exactly one of `conversation.goal_achieved` or
`conversation.goal_failed` per call, never both, with payload `reason`.
Calls with no actionable goal (information-only) MUST be verdicted as
`conversation.goal_achieved`.

#### Scenario: Actionable call with resolved goal

- GIVEN a transcript where the caller's stated problem was resolved
- WHEN the judge completes successfully
- THEN exactly one `conversation.goal_achieved` event is appended with a
  non-empty `reason`
- AND no `conversation.goal_failed` event is appended

#### Scenario: Actionable call with unresolved goal

- GIVEN a transcript where the caller's stated problem was not resolved
- WHEN the judge completes successfully
- THEN exactly one `conversation.goal_failed` event is appended with a
  non-empty `reason`
- AND no `conversation.goal_achieved` event is appended

#### Scenario: Information-only call defaults to goal_achieved

- GIVEN a transcript with no actionable caller goal (pure information
  exchange)
- WHEN the judge completes successfully
- THEN exactly one `conversation.goal_achieved` event is appended with a
  `reason` reflecting the information-only nature of the call
- AND no `conversation.goal_failed` event is appended

### Requirement: Judge failures are isolated and bounded

The system MUST retry a failing judge call (rate limit, timeout, or
malformed/unparseable output) up to a maximum of 3 attempts. Malformed or
unparseable judge output MUST be treated as a failed attempt. After 3 failed
attempts, the system MUST emit zero signal events for that call and MUST NOT
raise an error that blocks or corrupts content derivation or the post-terminal
build.

#### Scenario: Judge succeeds on retry within the attempt budget

- GIVEN the first judge call times out and the second attempt succeeds
- WHEN the post-terminal build runs
- THEN the signal events derived from the successful second attempt are
  appended
- AND no more than 2 attempts were made

#### Scenario: Judge exhausts retries and yields no signals

- GIVEN the judge fails on all 3 attempts (timeout, rate limit, or malformed
  output, in any combination)
- WHEN the post-terminal build runs
- THEN zero `conversation.topic_change`, `conversation.goal_achieved`, or
  `conversation.goal_failed` events are appended
- AND content events derived earlier in the same build remain intact
- AND the post-terminal build does not fail or raise

#### Scenario: Malformed judge output counts as a failed attempt

- GIVEN the judge returns a reply that cannot be parsed into the expected
  structured output
- WHEN that attempt is evaluated
- THEN it is counted as one of the 3 failed attempts
- AND no signal events are derived from that unparseable reply

### Requirement: Retry-safe idempotent identity for signal events

Each signal event's identity MUST be a UUID5 fingerprint derived from stable
canonical fields — `session_id`, `event_type`, and the verdict/count content
(e.g. topic list, goal outcome) — explicitly excluding timestamps and raw
delivery/provenance identifiers, analogous to the content-event identity
approach. Re-processing the same report, or a provider webhook redelivery,
MUST NOT create duplicate signal events.

#### Scenario: Reprocessing the same report is idempotent

- GIVEN signal events were already derived and persisted for a session
- WHEN the same `end-of-call-report` is processed again for that session
- THEN no new signal events are created
- AND the existing signal events are left unchanged

#### Scenario: Provider redelivers the end-of-call-report webhook

- GIVEN a session whose signal events were already derived
- WHEN the webhook is redelivered (duplicate delivery, different raw
  delivery id)
- THEN the derived signal events resolve to the same UUID5 identities
- AND no duplicate rows are persisted

### Requirement: Signal derivation does not mutate session lifecycle

Appending signal events MUST be valid only once the session is no longer
ACTIVE (ENDED or FAILED), and MUST NOT change `status` or `ended_at`.

#### Scenario: Signal events append to an already-terminal session

- GIVEN a session already in ENDED or FAILED status
- WHEN signal events are appended
- THEN the append succeeds
- AND `status` and `ended_at` remain unchanged
