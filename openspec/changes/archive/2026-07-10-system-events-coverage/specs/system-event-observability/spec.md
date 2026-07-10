# System Event Observability Specification

## Purpose

Define trustworthy, retry-safe production and verification of canonical `system.*` governance events while preserving Vapi payloads in raw storage.

## Requirements

### Requirement: Measure Platform Latency

The system MUST emit `system.latency_measured` from platform-recorded timestamps for webhook ingestion and evaluation work. Each event SHALL identify the measured operation, duration, unit, source timestamps, and linked session/report when available. It MUST NOT claim provider-side latency.

#### Scenario: Measure webhook ingestion

- GIVEN a webhook has platform receipt and completion timestamps and a resolved session
- WHEN ingestion completes
- THEN one latency event records the elapsed duration and operation provenance

#### Scenario: Missing correlation

- GIVEN an operation has no resolvable session identity
- WHEN its latency is measured
- THEN no canonical event is persisted and the condition is logged

### Requirement: Preserve Model Invocation Mapping

The system MUST continue to promote Vapi `model-output` messages as `system.model_invocation` with provider provenance. This mapping is verification-only and MUST NOT be replaced by an internally inferred invocation.

#### Scenario: Map model output

- GIVEN a valid Vapi `model-output` message
- WHEN the message is ingested
- THEN the canonical event is `system.model_invocation` and retains its provider source

#### Scenario: Unsupported provider message

- GIVEN a non-`model-output` provider message without a safe canonical mapping
- WHEN it is ingested
- THEN it remains raw-only and does not create a model invocation

### Requirement: Record Correlated System Errors

The system MUST emit `system.error` for classified Vapi `endedReason` failures and recoverable internal errors. Error events SHALL include source, stable identity, classification, reason, and session/report linkage when available. A terminal failure MUST emit at most one correlated error across retries and MUST NOT replace, duplicate, or transition `session.failed`.

#### Scenario: Correlate terminal failure

- GIVEN an end-of-call report classifies as a terminal failure for an active session
- WHEN it is processed
- THEN one correlated system error and the existing `session.failed` lifecycle event are recorded

#### Scenario: Retry terminal report

- GIVEN the same terminal report is retried
- WHEN it is processed again
- THEN no duplicate system error or lifecycle transition is created

#### Scenario: Recoverable internal failure

- GIVEN a non-terminal internal operation fails with a resolved session
- WHEN the failure is handled
- THEN one error event is recorded without changing session lifecycle state

### Requirement: Preserve Warning Mapping

The system MUST continue to map Vapi `hang` messages and qualified anomalous signals to `system.warning`; this change SHALL verify, not replace, existing warning behavior.

#### Scenario: Map hang warning

- GIVEN a Vapi `hang` message for a resolved session
- WHEN it is ingested
- THEN a warning event retains provider provenance

### Requirement: Raise Governance Flags

The system MUST emit `system.flag_raised` for Vapi transcript `detectedThreats` and platform analysis findings. Transcript-derived flags MUST be appendable while the session is active and SHALL NOT alter lifecycle state or `ended_at`. Each flag SHALL contain source, stable identity, code, reason, and report linkage when available. Retries MUST NOT duplicate the same finding.

#### Scenario: Promote detected threats

- GIVEN a transcript includes one or more detected threats for a resolved session
- WHEN it is ingested
- THEN a flag event records each normalized finding with provider provenance

#### Scenario: Promote mid-call detected threats

- GIVEN an active session receives a Vapi transcript with a normalized detected threat
- WHEN the webhook is ingested
- THEN the raw delivery and exactly one `system.flag_raised` are persisted without changing session status or `ended_at`

#### Scenario: Repeat threat delivery

- GIVEN an already-recorded threat finding is delivered again
- WHEN it is processed
- THEN no duplicate flag event is persisted

#### Scenario: Platform analysis finding

- GIVEN platform analysis produces a governance finding for a resolved report
- WHEN the finding is accepted
- THEN a flag event records platform provenance and report linkage
