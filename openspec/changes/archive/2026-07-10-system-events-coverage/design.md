# Design: System Event Coverage

## Technical Approach

Keep Vapi as an input adapter and immutable `raw_events` landing unchanged. Add `RecordSystemObservation` for `system.latency_measured`, `system.error`, and `system.flag_raised`; `session.failed` stays on `IngestEvent` and is the sole lifecycle transition. The webhook explicitly assigns and flushes a `RawEvent` UUID before mapping, so promoted events retain raw provenance. Missing safe correlation means raw-only plus logging.

## Architecture Decisions

| Decision | Choice | Alternative / rationale |
|---|---|---|
| Boundary | Application use case + repository port | Do not emit from FastAPI/Celery directly; adapters only translate/orchestrate. |
| Observation lifecycle boundary | `Session.append_system_observation` permits `system.flag_raised` while active and all three new `system.*` types after terminal state, never changing status | Vapi transcript threats arrive mid-call; latency/error remain post-terminal while lifecycle markers remain separate. |
| Identity | UUID5 from a canonical content fingerprint; raw/event UUIDs are provenance, not retry keys | Provider timestamps can fall back to `now`, and raw UUIDs change per delivery, so neither is a dedupe identity. |
| Sequence invariant | Serialize *all* canonical appends per session, and add `UNIQUE(session_id, sequence_number)` | Locking only observations cannot protect the current unlocked `IngestEvent` path. |

## Data Flow

    webhook -> RawEvent(id assigned + flush) -> mapping intents -> serialized append
                                                        ├─ IngestEvent: ended/failed
                                                        └─ RecordSystemObservation
    Celery evaluation -> timing/errors/findings --------------------┘
                                                        |
                                             Session aggregate -> events

`vapi_mapping.py` preserves `model-output` → `system.model_invocation` and `hang`/qualified anomalies → `system.warning`. Pure helpers add: (1) a terminal-error intent only when existing failure classification returns `SESSION_FAILED`; (2) one threat intent per normalized `detectedThreats` entry, valid while the session is active. Unsupported/specialized messages remain raw-only. The webhook measures local monotonic receipt/completion timing after the main transaction succeeds, then performs a best-effort separate latency transaction; it never claims provider latency. Celery measures `evidence_evaluation`; recoverable failures and accepted platform findings use the same use case. The error wrapper only logs its own persistence failure, preventing recursion.

## Interfaces / Contracts

```python
@dataclass(frozen=True, slots=True)
class SystemObservationCommand:
    session_id: str
    event_type: EventType
    source: Source
    timestamp: datetime
    identity: str             # UUID5 input
    raw_event_id: UUID | None # provenance only
    payload: dict[str, Any]

class GovernanceRepository(Protocol):
    async def get_session_for_update(self, session_id: str) -> Session | None: ...
    async def append_event(self, event: Event) -> bool: ...
```

Both `IngestEvent` and `RecordSystemObservation` use `get_session_for_update` (`SELECT ... FOR UPDATE`) before sequence assignment; new-session insert races retry by reloading under lock. `append_event` inserts with `ON CONFLICT (event_id) DO NOTHING`. Add the `(session_id, sequence_number)` unique constraint to `EventModel` and Alembic; this is a defense-in-depth invariant and requires a migration.

The UUID5 identity uses a versioned SHA-256 canonical JSON fingerprint, never a provider timestamp or unspecified key. Terminal error: `call_id`, normalized `endedReason`, and canonical report fields. Threat: `call_id`, `transcriptType`, normalized transcript text hash, normalized threat `code` and `reason`; its `raw_event_id` is payload provenance. Latency: operation plus the already-persisted canonical event ID that completed ingestion; evaluation/error/finding identities use an explicit operation/run/finding input. If required stable fields are absent, no system event is promoted. Payloads include identity, raw/canonical links, operation/classification or code/reason, and report ID when available.

For a terminal report, the endpoint appends correlated `system.error` and `session.failed` within the *same* database transaction and commits once. Any insert/flush failure rolls back raw, error, and lifecycle changes; no partial error may suppress the failure transition. A retry uses the same error identity, while the terminal lifecycle path remains idempotent.

## File Changes

| File | Action | Description |
|---|---|---|
| `backend/src/domain/session.py` | Modify | Validated non-lifecycle system observation. |
| `backend/src/application/commands.py` | Modify | Immutable observation command. |
| `backend/src/application/use_cases/record_system_observation.py` | Create | Resolve, fingerprint, and append. |
| `backend/src/application/use_cases/ingest_event.py` | Modify | Use serialized canonical append path. |
| `backend/src/application/ports/governance_repository.py` | Modify | Locked lookup and idempotent append. |
| `backend/src/infrastructure/repositories/governance_repository.py` | Modify | Lock/retry/PK conflict implementation. |
| `backend/src/infrastructure/db/models.py` + new Alembic revision | Modify/Create | Sequence uniqueness invariant. |
| `backend/src/adapters/rest/vapi_mapping.py`, `vapi.py` | Modify | Stable derivatives, raw provenance, timing, atomic terminal flow. |
| `backend/src/infrastructure/celery/tasks.py` | Modify | Evaluation latency/findings and non-recursive errors. |
| Focused domain/use-case/repository/webhook/task tests | Modify/Create | Strict-TDD coverage. |

## Testing Strategy

| Layer | What to test | Approach |
|---|---|---|
| Domain | Allowed types preserve lifecycle | RED unit tests. |
| Repository | Concurrent normal + system appends retain unique ordered sequences | Async PostgreSQL integration test. |
| Mapping | Canonical fingerprints, raw links, absent stable fields → raw-only | Unit tests; no `now` identity. |
| Webhook | One terminal error plus failed; injected second insert failure rolls back both | Transaction integration test. |
| Celery | Latency/errors/findings and error-emitter recursion guard | Task tests. |

## Migration / Rollout

Add and deploy the sequence-uniqueness migration (after checking/deduplicating any historical collisions) before application rollout. The existing marker-index migration remains a prerequisite. Rollback reverts emitters and the new constraint only after checking consumers; raw landing and current mappings remain intact.

## Open Questions

None.
