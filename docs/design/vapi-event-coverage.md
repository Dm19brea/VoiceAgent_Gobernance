# Vapi event coverage against the canonical governance taxonomy

This document tracks how each canonical `EventType` from `backend/src/domain/enums.py` is currently populated: directly from Vapi webhooks, inferred by platform logic, or still pending.

## Current coverage

| event_type | Stored from Vapi | Inferred by platform logic | Vapi webhook that currently produces it | Current status / next step |
|---|---:|---:|---|---|
| `session.started` | Yes | No | `status-update` with `status=in-progress`; `assistant.started` | Implemented. |
| `session.ended` | Yes | No | `end-of-call-report` | Implemented. `end-of-call-report` is authoritative because it carries final evidence. |
| `session.failed` | Yes | Yes | `end-of-call-report` (via `classify_terminal_event`) | Implemented. Classified from `endedReason` on `end-of-call-report`; see `classify_terminal_event` in `backend/src/adapters/rest/vapi_mapping.py`. |
| `session.evaluation_triggered` | No | Yes | N/A — platform-emitted marker (not from a Vapi webhook) | Implemented. Appended post-terminal at the start of `build_session_evidences_async`; see `RecordEvaluationTriggered` in `backend/src/application/use_cases/record_evaluation_triggered.py` and `Session.append_marker` in `backend/src/domain/session.py`. |
| `conversation.turn_started` | Yes | No | `speech-update` with `status=started` | Implemented. Source comes from `role` when present. |
| `conversation.turn_ended` | Yes | No | `speech-update` with `status=stopped` | Implemented. Source comes from `role` when present. |
| `conversation.agent_response` | Yes | No | `assistant.speechStarted`; `transcript` with `role=assistant`; `conversation-update` with `role=assistant`; `speech-update` with `role=assistant` and no status | Implemented. |
| `conversation.user_input` | Yes | No | `transcript` with `role=user`; `conversation-update` with `role=user`; `speech-update` with `role=user` and no status | Implemented. |
| `conversation.silence_detected` | No | Yes | None | Pending. Needs platform-side detection or a provider signal not currently mapped. |
| `conversation.interruption_detected` | Yes | No | `user-interrupted` | Implemented. |
| `conversation.topic_change` | No | Yes | None | Pending. Requires conversation analysis/business logic. |
| `conversation.goal_achieved` | No | Yes | None | Pending. Requires outcome/evaluation logic. |
| `conversation.goal_failed` | No | Yes | None | Pending. Requires outcome/evaluation logic. |
| `tool.called` | Yes | No | `tool-calls`; `transfer-destination-request`; `knowledge-base-request`; `phone-call-control`; `voice-input`; `voice-request`; `call.endpointing.request` | Implemented as provider interaction tracking. Next: decide whether custom voice/endpointing should stay under `tool.called` or get finer-grained events. |
| `tool.response_received` | No | Yes | None | Pending. Requires registering tool execution responses. |
| `tool.failed` | No | Yes | None | Pending. Requires tool execution error handling. |
| `tool.timeout` | No | Yes | None | Pending. Requires timeout instrumentation. |
| `tool.retry` | No | Yes | None | Pending. Requires retry instrumentation. |
| `system.latency_measured` | No | Yes | None | Pending. Requires latency measurement in the platform. |
| `system.model_invocation` | Yes | No | `model-output` | Implemented. |
| `system.error` | No | Yes | None | Pending. Requires platform/provider error classification. |
| `system.warning` | Yes | Yes | `transfer-update`; `language-change-detected`; `hang`; `chat.*`; `session.*` | Implemented for broad provider warnings. Next: refine if these become too noisy. |
| `system.flag_raised` | No | Yes | None | Pending. Requires governance/risk rule detection. |

## Mapping rules to preserve

- Every Vapi payload is still stored raw first.
- A Vapi payload is promoted to a canonical event only when it has a safe domain meaning.
- `status-update` with `ended`, `failed`, or `error` is intentionally raw-only for now.
- `end-of-call-report` is the canonical terminal event because it carries the final report evidence.

## Next step

Map and register the pending platform-inferred events without inventing semantics from Vapi payloads. The next implementation slice should define where each pending event is emitted in the platform lifecycle, then add tests before production code.
