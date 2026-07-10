# Proposal: System Event Coverage

## Intent

Complete pending `system.*` coverage with locked Vapi/platform sources; preserve raw landing.

## Scope

### In Scope
- Emit `system.latency_measured` internally from workflow timestamps for webhook ingestion and evaluation.
- Emit `system.error` from Vapi `endedReason` and recoverable internal errors. A terminal failure emits one correlated error alongside, never instead of, `session.failed`; retries share identity.
- Emit `system.flag_raised` from transcript threats and platform flags, with source, code, reason, and report linkage.
- Verify implemented `model-output` → invocation and `hang`/anomalies → warning mappings without reimplementing them.
- Add domain/application paths, port support, TDD tests, and coverage updates.

### Out of Scope
- `session.*`, `conversation.*`, and `tool.*`, including Vapi evals (mock testing only).
- Replacing `system.model_invocation` or `system.warning` mappings.
- Responding to assistant/tool/transfer/knowledge-base/function/handoff requests.
- Dedicated voice/endpointing endpoints, authentication, dashboards, or provider-side latency claims.

## Capabilities

### New Capabilities
- `system-event-observability`: latency, correlated error, and flag production with provenance and idempotency.

### Modified Capabilities
- None.

## Approach

Preserve raw landing. Keep `model-output` → invocation and `hang` → warning; anomalous signals may add warnings. Extend mapping for transcript threats and terminal `endedReason`; use a domain-approved path for timestamps and internal errors/flags. Correlate terminal error to its call/report, while `session.failed` remains the only lifecycle transition. Persist stable identities; without session identity, log only.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `backend/src/adapters/rest/vapi_mapping.py` | Modified | Threat/error classification. |
| `backend/src/adapters/rest/vapi.py` | Modified | Timestamp latency and recoverable-failure emission. |
| `backend/src/application/` | Modified | Use cases and port. |
| `backend/src/infrastructure/celery/tasks.py` | Modified | Evaluation timing/errors/flags. |
| `backend/tests/` | Modified | Strict-TDD coverage. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---:|---|
| Recursive error recording | Med | Best-effort non-recursive emitter and logs. |
| Noisy metrics/flags | Med | Explicit operation and threat schemas. |
| Retry duplicates | Med | Stable identity plus database idempotency. |

## Rollback Plan

Revert new emitters/use cases and any persistence migration; raw landing, existing model/warning mappings, and session closure remain unchanged.

## Dependencies

- Locked sources: timestamps → latency; `model-output` → invocation; `endedReason`/internal → error; `hang`/anomalies → warning; transcript threats/analysis → flag.
- Vapi messages require provider configuration.
- Existing `session-lifecycle-events` work is a prerequisite baseline, not part of this change.

## Success Criteria

- [ ] Latency, error, and flag events have locked sources, structured payloads, and retry-safe identities.
- [ ] Terminal failures produce correlated `system.error` plus `session.failed`, without replacing or duplicating lifecycle.
- [ ] Model/warning source mappings are verified; unsupported/specialized messages remain raw.
- [ ] Retries do not duplicate system events; terminal behavior remains unchanged.
- [ ] Focused and full backend tests pass.
