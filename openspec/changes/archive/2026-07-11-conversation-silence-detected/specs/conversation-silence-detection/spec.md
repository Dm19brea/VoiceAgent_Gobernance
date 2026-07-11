# Conversation Silence Detection Specification

## Purpose

Define deterministic, post-terminal evidence for prolonged interior pauses while waiting for a user response.

## Requirements

### Requirement: Qualifying user-response silence

The system MUST evaluate only consecutive assistant-to-user turn boundaries from the end-of-call report. A gap MUST qualify when the subsequent user turn starts at least 6 seconds after the preceding assistant turn ends.

#### Scenario: Gap exceeds the threshold

- GIVEN a valid assistant turn ending at 10 seconds and the next user turn starting at 17 seconds
- WHEN post-terminal silence detection runs
- THEN the 7-second gap MUST qualify

#### Scenario: Exact threshold qualifies

- GIVEN a valid assistant turn ending exactly 6 seconds before the next user turn starts
- WHEN post-terminal silence detection runs
- THEN the gap MUST qualify

### Requirement: Scope exclusions

The system MUST NOT classify user-to-assistant latency, pre-first-turn time, post-last-turn time, terminal silence, or a `silence-timed-out` outcome as a qualifying interval. A qualifying interval MUST have an actual subsequent user response.

#### Scenario: Agent response latency is excluded

- GIVEN a user turn followed 8 seconds later by an assistant turn
- WHEN silence detection runs
- THEN no qualifying user-response silence MUST be derived from that boundary

#### Scenario: Terminal silence is excluded

- GIVEN an assistant turn with no subsequent user response and a call ending for `silence-timed-out`
- WHEN silence detection runs
- THEN no qualifying interval MUST be derived from the terminal gap or outcome

### Requirement: Single aggregated event

The system MUST emit no `conversation.silence_detected` event when zero intervals qualify. When one or more intervals qualify, it MUST append at most one event per call containing the total qualifying count and auditable data for every counted interval, including its duration, chronological boundaries, and adjacent turn references. The event MUST record the 6-second threshold policy used.

#### Scenario: No qualifying gaps

- GIVEN all valid assistant-to-user interior gaps are shorter than 6 seconds
- WHEN silence detection runs
- THEN no `conversation.silence_detected` event MUST be appended

#### Scenario: Multiple gaps are aggregated

- GIVEN one call has three valid assistant-to-user gaps of 6, 8, and 11 seconds
- WHEN silence detection runs
- THEN exactly one event MUST be appended with a total count of 3
- AND its audit data MUST describe all three intervals

### Requirement: Trustworthy timing only

The system MUST NOT fabricate an interval when either required boundary is missing, malformed, non-finite, negative, or chronologically inconsistent. Skipping untrustworthy timing MUST NOT prevent other valid post-terminal derivations from completing.

#### Scenario: Malformed boundary is isolated

- GIVEN one candidate boundary lacks a valid assistant end time and another post-terminal derivation is valid
- WHEN enrichment runs
- THEN no silence interval MUST be inferred from the malformed boundary
- AND the other derivation MUST still complete

### Requirement: Retry-safe canonical persistence

The aggregated event MUST have a deterministic identity for the call, event type, and detector policy. Reprocessing or redelivery of equivalent source data MUST NOT append a duplicate event.

#### Scenario: End-of-call report is redelivered

- GIVEN a report that produces one aggregated silence event has already been processed
- WHEN the equivalent report is processed again
- THEN the persisted call MUST still contain exactly one `conversation.silence_detected` event

### Requirement: Append-only temporal semantics

The event `sequence_number` MUST represent ingestion order. Its `timestamp` MUST represent the chronology of the detected silence evidence and MAY precede terminal events even when appended after them.

#### Scenario: Post-terminal append preserves both orders

- GIVEN qualifying silence occurred before session termination
- WHEN its aggregate event is appended post-terminal
- THEN its sequence number MUST follow previously persisted events
- AND its timestamp MUST remain chronologically tied to the detected silence evidence
