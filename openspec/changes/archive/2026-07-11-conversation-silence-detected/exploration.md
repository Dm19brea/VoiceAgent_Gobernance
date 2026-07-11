## Exploration: `conversation.silence_detected`

### Current State

`conversation.silence_detected` exists in the canonical `EventType` taxonomy but has no producer, use case, persisted payload contract, or dedicated tests. This is deliberate: prior work deferred it until the business meaning of “silence” was defined—especially the threshold and whether user response delay and agent response latency are the same governance fact.

The strongest data already retained is the terminal Vapi `end-of-call-report`. Its `artifact.messages` entries expose turn timing (`time`, `endTime`, `duration`, `secondsFromStart`), and the established design identifies the gap from one turn's `endTime` to the next turn's `time` as derivable silence. Current code only consolidates each role-run's first `time`; it does not yet preserve `endTime` because content derivation only needs turn starts.

`speech-update` currently drives only the transient live speaking indicator. `turn_started` and `turn_ended` are intentionally not persisted. Vapi `endedReason = silence-timed-out` is already used by scoring as a terminal report outcome, but current code contains no explicit provider message representing each silence interval.

Any post-terminal implementation must preserve C1 append-only semantics: `sequence_number` is ingestion/provenance order, while `timestamp` is the chronological occurrence time. Derived silence events may therefore be appended after `session.ended` while carrying an earlier timestamp.

### Affected Areas

- `backend/src/domain/enums.py` — taxonomy already contains `CONVERSATION_SILENCE_DETECTED`; no enum change is needed.
- `backend/src/adapters/rest/vapi_mapping.py` — report timing parsing/consolidation currently retains turn start only; a deterministic report-gap detector would need start and end boundaries.
- `backend/src/infrastructure/celery/tasks.py` — existing isolated post-terminal enrichment pipeline is the natural integration point for report-derived events.
- `backend/src/application/commands.py` and `backend/src/application/use_cases/` — would need a retry-safe silence command/recorder with deterministic identity.
- `backend/src/domain/session.py` — post-terminal append allowlist currently covers content and LLM-judge signals, not silence observations.
- `backend/src/infrastructure/redis/active_sessions.py` — contains live speaking state only; relevant solely to the real-time timer option.
- `backend/src/domain/scoring/catalogue.py` — recognizes terminal `silence-timed-out`, which is not equivalent to per-occurrence canonical silence.
- `backend/tests/test_conversation_content_mapping.py`, `backend/tests/test_build_evidences_task.py`, and new silence-specific unit/integration tests — timing normalization, thresholds, identity, retries, and ordering need coverage.
- `docs/design/conversation-events-from-end-of-call-report.md` — records the prior deferral, report-gap source, and append-only ordering decision.

### Approaches

1. **Post-terminal deterministic derivation from report timing gaps** — after call close, calculate each interior gap from the previous consolidated turn's `endTime` to the next turn's `time`, and emit only gaps meeting configured governance rules.
   - Definition of silence: an interior no-speech interval between two valid consecutive turns. Classify it by expected responder: `waiting_for_user` when an assistant turn is followed by a user turn, and `agent_response_latency` when a user turn is followed by an assistant turn. The proposal must decide whether both classifications are canonical silence or whether agent latency belongs only under `system.latency_measured`.
   - Source of truth: immutable `end-of-call-report.artifact.messages` timing, consolidated by role-run to avoid treating Vapi fragments as separate turns.
   - Threshold/configuration: explicit versioned policy, preferably separate thresholds by classification rather than one global number. Exclude negative/overlapping gaps and entries without trustworthy start/end times. Decide separately whether pre-first-turn and post-last-turn gaps are in scope; safest first slice is interior gaps only.
   - Payload: `duration_milliseconds`, `classification`, `threshold_milliseconds`, `previous_turn_index`, `next_turn_index`, `started_at`, `ended_at`, `detector: "report_gap"`, `detector_version`, and deterministic `identity`.
   - Idempotency: UUID5 over session, event type, detector/schema version, classification, adjacent stable turn indexes, and normalized gap boundaries. Threshold should be recorded in payload/policy version; changing policy must have an explicit reprocessing/versioning decision.
   - Ordering/timestamp: append post-terminal. Use silence start (previous turn `endTime`) as event timestamp; sequence number remains append order. Chronological consumers order by timestamp.
   - False positives/negatives: low-to-medium. Fragment consolidation or missing/inaccurate `endTime` can distort gaps; endpointing and network timing may appear as conversational silence. Excluding incomplete boundaries reduces false positives but creates false negatives.
   - Operational complexity: Medium. Reuses the proven report/Celery/retry-safe append pattern and requires no live timers or new provider subscription.
   - Testability: High. Pure detector tests can cover exact threshold boundaries, role classification, fragments, missing/invalid timing, overlap, multiple gaps, duplicate reprocessing, and append-only timestamp semantics.
   - Pros: deterministic, replayable, auditable, no new runtime state, and based on data already retained.
   - Cons: delayed until call close and dependent on timing quality; business classification and thresholds still must be chosen.
   - Effort: Medium.

2. **Real-time state/timer derivation from `speech-update`** — start a deadline when speech stops and emit when no subsequent speech starts before the configured threshold.
   - Definition of silence: elapsed wall-clock/event-time inactivity after a `speech-update status=stopped`, classified from the role that stopped and the expected next speaker.
   - Source of truth: transient ordered `speech-update` state plus a platform timer; Redis would hold detector state, not canonical truth.
   - Threshold/configuration: separate inactivity thresholds by expected responder; timer cancellation, replacement, session-end behavior, and late/out-of-order event tolerance must be specified.
   - Payload: `duration_milliseconds` at detection, `classification`, `threshold_milliseconds`, preceding role, `started_at`, `detected_at`, `detector: "realtime_timer"`, detector version, and identity.
   - Idempotency: UUID5 over session, detector version, and a stable preceding `speech-update` occurrence key. Without a provider event ID or stable timestamp, retry-safe identity is weaker; timer retries must not emit twice.
   - Ordering/timestamp: can persist while the session is active when the threshold expires. Timestamp should be the moment the interval crossed the threshold (silence start plus threshold), not worker execution time. A later speech start may reveal total duration but must not mutate the immutable event unless the payload contract deliberately stores only threshold breach.
   - False positives/negatives: medium-to-high due to dropped/reordered updates, stuck speaking state, worker restarts, Redis loss, endpointing behavior, and pauses caused by tools or transfers.
   - Operational complexity: High. Requires durable scheduling or recovery, atomic state transitions, cancellation, restart reconciliation, and separation from the cosmetic live indicator.
   - Testability: Medium. Fake-clock state-machine tests are feasible, but race, restart, duplicate, loss, and event-order scenarios are extensive.
   - Pros: immediate detection can power intervention/alerting during the call.
   - Cons: operationally expensive and less reproducible than report derivation; risks turning a best-effort live channel into governance truth.
   - Effort: High.

3. **Provider/analysis-assisted terminal classification** — treat an explicit provider outcome such as `endedReason = silence-timed-out`, or a future supported Vapi analysis field, as the authoritative signal for a narrower silence definition.
   - Definition of silence: not every conversational pause; only provider-confirmed terminal abandonment/time-out due to silence. A transcript LLM alone is not sufficient because text does not encode elapsed silence.
   - Source of truth: current terminal `endedReason` for `silence-timed-out`; richer per-occurrence provider analysis only if a real payload field is later verified. Current repository evidence shows no explicit per-gap provider signal.
   - Threshold/configuration: owned by Vapi/assistant timeout configuration rather than the governance backend. The platform should record the observed provider reason and, if available, the configured timeout value/version.
   - Payload: `classification: "terminal_silence_timeout"`, `provider`, `provider_reason`, optional `configured_timeout_milliseconds`, terminal timestamp, provenance/raw event ID, and deterministic identity.
   - Idempotency: one deterministic UUID5 per session, event type, and normalized provider reason; a DB uniqueness rule per session/type may also be appropriate because this definition allows at most one terminal occurrence.
   - Ordering/timestamp: derive post-terminal and append after closure. Use the provider terminal timestamp; sequence number remains ingestion order.
   - False positives/negatives: low false positives for the narrow terminal definition, but extremely high false negatives if the intended metric is all prolonged pauses. Provider timeout can also reflect call abandonment rather than a conversational quality issue.
   - Operational complexity: Low for `silence-timed-out`; unknown/high if dependent on a future provider analysis capability.
   - Testability: High for terminal reason mapping and duplicate reports; currently impossible to validate richer per-gap behavior because no such field is evidenced in code or fixtures.
   - Pros: explicit and simple for terminal silence, minimal detector logic.
   - Cons: semantically narrow, provider-coupled, and cannot support prolonged-silence rate across a conversation.
   - Effort: Low for terminal-only semantics; otherwise blocked on provider evidence.

### Recommendation

Recommend **Approach 1: post-terminal deterministic derivation from report timing gaps** for a general canonical silence event. It is the only option that is both replayable and capable of representing every measurable prolonged pause without promoting the transient live channel to source of truth.

This recommendation does not decide the product semantics. Before proposal, the user must choose whether `conversation.silence_detected` means (a) user-response silence only, (b) both user-response silence and agent-response latency with an explicit classification, or (c) only terminal provider timeouts. The threshold or threshold policy must also be selected.

### Risks

- The largest risk is semantic: counting agent latency as conversational silence may duplicate or conflict with `system.latency_measured`.
- Current consolidation keeps turn start but not turn end; fragmented Vapi messages require a proven rule for the consolidated turn's final `endTime`.
- Missing or malformed timing must produce no canonical event rather than a guessed duration.
- Reprocessing under a changed threshold can change the event set; policy versioning and backfill behavior must be explicit.
- Terminal gaps and pre-first-turn gaps are less reliable than interior gaps and should not silently enter the first slice.
- The previous `conversation-interruption-detected` exploration is obsolete due to corrected scope and must not inform this proposal.

### Ready for Proposal

No. The code paths and three options are understood, but proposal must wait for the user to choose an approach, define which silence classification(s) count, and set the threshold policy.
