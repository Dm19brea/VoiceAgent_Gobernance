# M3 — Evidence construction (SDD)

Change name: `m3-evidence-construction` · Store: engram · Mode: interactive

## 1. Proposal

### Intent
Transform a completed session's event trace into structured **Evidences** (doc 3.2) — the bridge
from raw events to evaluation (M4). When a session closes, an asynchronous worker builds the
evidences and persists them, without blocking the webhook response.

### Confirmed design decisions
1. **Async mechanism: Celery + Redis** (roadmap M3.3). Built and tested locally (Redis is already
   in `docker-compose`); tests run Celery in eager mode. Deploying the worker to Railway is a
   separate infra decision, deferred — so M3 has **no Railway cost**.
2. **Rich evidences.** In addition to turn counts and duration from the canonical events, mine the
   Vapi `end-of-call-report` payload (real duration, ended reason, summary, transcript). Far more
   material to evaluate in M4. Normalisation keeps the domain decoupled from Vapi.

### Scope (M3.1–M3.5)
| Sub | Deliverable |
|-----|-------------|
| M3.1 | `Evidence` entity (domain, pure) |
| M3.2 | Evidence construction service (sync, pure): session events → evidences. No Redis. |
| M3.3 | Celery + Redis wiring (trivial task first) |
| M3.4 | Real construction task triggered on `session.ended`; persist evidences |
| M3.5 | Decouple the endpoint: enqueue the task, respond fast |

### Evidence types (doc 3.2)
`direct` (from a single event), `inferred` (computed over several events), `composite`
(combining evidences).

### Approach (hexagonal, inside-out)
`Evidence` entity + construction service pure first (TDD, no Redis), then a Celery task wraps the
service, then it is triggered when a session closes. The service depends on the repository port,
never on Celery or SQLAlchemy.

### Out of scope (deferred)
- Metric normalisation + scoring (M4).
- Deploying the Celery worker to Railway (infra decision; local dev uses docker-compose Redis).

### Open questions (resolve in design)
- The concrete catalogue of criteria/evidences buildable from our canonical events +
  `end-of-call-report`.
- How to normalise Vapi's `end-of-call-report` fields into evidence inputs without leaking Vapi
  into the domain (likely a small extraction at the adapter or a normalised payload).
- Repository port extension for persisting/reading evidences.

### Risks
- Celery + Redis adds an async moving part; tests must isolate it (eager mode).
- `end-of-call-report` shape varies across calls; mining must degrade gracefully on missing fields.

## 2. Spec

### Requirements

- **R1 — Evidence entity.** Fields per doc 3.2: `evidence_id`, `session_id`, `evidence_type`
  (`direct`/`inferred`/`composite`), `criterion`, `conclusion`, `value` (nullable), `dimension`
  (`conversational`/`operational`/`technical`/`risk`), `source_events` (list of `event_id`),
  `generated_at`. Immutable. Traceable: `source_events` grounds every evidence in real events.
- **R2 — Construction service.** Given a `Session` with its events, produce a list of Evidences by
  applying predefined criteria. **Pure** (no Redis, no DB) and **deterministic** (same trace →
  same evidences, doc 3.2 reproducibility).
- **R3 — Direct evidences.** At least: *session completed* (from `session.ended`) and *ended
  reason* (from the `end-of-call-report` payload). Each references its source event(s).
- **R4 — Inferred evidences.** Turn counts (total / agent / user) and session duration, computed
  over the trace.
- **R5 — Normalisation.** `end-of-call-report` fields (duration, ended reason, summary) are read
  through a normalisation step, so the construction service consumes normalised inputs, not raw
  Vapi keys — the domain stays decoupled from Vapi.
- **R6 — Repository port.** Extended to persist evidences (`add_evidences`) and read them
  (`get_evidences_by_session`).
- **R7 — Async trigger.** When ingestion records a `session.ended` (the session closes), a Celery
  task is enqueued to build + persist the evidences for that session. The webhook response is not
  blocked.
- **R8 — Graceful degradation.** Missing `end-of-call-report` fields do not crash the builder;
  the affected evidence is skipped or its `value` is null.

### Scenarios (become tests)

- **S1** An `Evidence` is immutable and carries `source_events` and a `dimension`.
- **S2** Given a closed session with N conversation events → an inferred evidence *total turns = N*
  referencing those events.
- **S3** Given a `session.ended` event whose payload has an ended reason → a direct evidence with
  that conclusion, referencing the event.
- **S4** Given `started_at` and `ended_at` → an inferred *duration* evidence with the value in
  seconds.
- **S5** Determinism: the same session yields the same set of evidences.
- **S6** The construction task, given a `session_id`, loads the session, builds evidences and
  persists them via the repository.
- **S7** On a `session.ended` ingestion the task is enqueued (not run inline); the webhook returns
  immediately.
- **S8** A `session.ended` with no ended-reason field does not crash the builder.

## 3. Design

### D1 — Evidence entity (domain, pure)
`domain/evidence.py`: frozen dataclass `Evidence` (per doc 3.2). New enums in `domain/enums.py`:
`EvidenceType` (`direct`/`inferred`/`composite`) and `Dimension`
(`conversational`/`operational`/`technical`/`risk`). Immutable; `source_events: list[UUID]`.

### D2 — Evidence catalogue for M3
Each criterion is a small pure function. M3 ships `direct` + `inferred` (composite deferred to M4,
where there is more to combine):

| Criterion | Type | Dimension | From |
|---|---|---|---|
| `session_completed` | direct | technical | `session.ended` present |
| `ended_reason` | direct | operational | normalised report |
| `total_turns` | inferred | conversational | count of `conversation.*` |
| `agent_turns` | inferred | conversational | count `conversation.agent_response` |
| `user_turns` | inferred | conversational | count `conversation.user_input` |
| `session_duration_seconds` | inferred | technical | `ended_at − started_at` |

### D3 — Construction service (domain, pure)
`domain/evidence_builder.py`: `build_evidences(session: Session) -> list[Evidence]`. Pure and
deterministic (no Redis, no DB, no clock beyond `generated_at`). Applies each criterion over the
session's events; every Evidence lists the `event_id`s it derives from (traceability, R1).

### D4 — Normalisation (keeps the domain Vapi-free)
The **adapter** (`vapi_mapping`) normalises the raw `end-of-call-report` into a `report` sub-dict
`{duration_seconds, ended_reason, summary}` placed in the command payload. The domain builder
reads only `event.payload["report"]` — a normalised contract, never Vapi keys. Raw Vapi stays in
`raw_events`. Missing fields → `None` (S8).

### D5 — Persistence
`EvidenceModel` (`infrastructure/db/models.py`): `evidence_id` PK, `session_id` FK, `evidence_type`,
`criterion`, `conclusion`, `value` (nullable float), `dimension`, `source_events` (JSONB uuid[]),
`generated_at`. One new Alembic migration. Repository port gains `add_evidences(list[Evidence])`
and `get_evidences_by_session(session_id) -> list[Evidence]`.

### D6 — Celery + Redis
`infrastructure/celery/app.py`: Celery app, broker/result backend = `REDIS_URL` (from settings).
Task `build_session_evidences(session_id: str)`: opens its **own** async DB session, loads the
session via the repository, runs `build_evidences`, persists via `add_evidences`, commits. Celery
is sync, so it drives the async repository with `asyncio.run(...)`. Tests run Celery in **eager
mode** (`task_always_eager=True`) — synchronous, no Redis needed.

### D7 — Trigger (decoupled from the web response)
When the Vapi webhook ingests a `session.ended` command, after the DB commit it enqueues
`build_session_evidences.delay(session_id)` and returns immediately (R7). Rebuilds are idempotent
(evidences replaced for the session).

### D8 — Layer placement
```
domain/          evidence.py · evidence_builder.py · enums (EvidenceType, Dimension)
application/     GovernanceRepository port += add_evidences / get_evidences_by_session
infrastructure/  EvidenceModel + migration · repo impl · celery/app.py + tasks
adapters/rest/   vapi_mapping normalises report · webhook enqueues on session.ended
```
Dependency rule holds: the builder is pure domain; Celery and SQLAlchemy stay in infrastructure.

## 4. Tasks

Test-first (RED → GREEN → REFACTOR). Grouped by subphase; each group ships as one commit.

### M3.1 — Evidence entity (`domain/`)
- [x] **T1** Enums `EvidenceType`, `Dimension`. Test: expected members.
- [x] **T2** `Evidence` frozen dataclass (doc 3.2 fields). Test: immutability, `source_events`,
  `dimension` (S1).

### M3.2 — Construction service (`domain/`, pure, no Redis)
- [ ] **T3** `build_evidences(session)` — inferred evidences: total/agent/user turns + duration
  (S2, S4). Tests with an in-memory Session.
- [ ] **T4** `build_evidences` — direct evidences: `session_completed`, `ended_reason` (from
  normalised `report`); graceful when absent (S3, S8); determinism (S5).

### M3.3 — Celery + Redis wiring (`infrastructure/celery/`)
- [ ] **T5** Celery app (broker/backend = `REDIS_URL`), `task_always_eager` in tests, trivial task
  to prove the wiring runs.

### M3.4 — Persistence + real task
- [ ] **T6** `EvidenceModel` + Alembic migration (apply to local Postgres).
- [ ] **T7** Port extension `add_evidences` / `get_evidences_by_session`; fake + SQLAlchemy impl.
- [ ] **T8** Task `build_session_evidences(session_id)`: load session → `build_evidences` →
  persist. Integration test (Celery eager, real DB) (S6).

### M3.5 — Normalisation + trigger (`adapters/rest/`)
- [ ] **T9** Normalise `end-of-call-report` → `report` sub-dict in `vapi_mapping`. Tests per field
  + graceful (D4).
- [ ] **T10** Webhook enqueues `build_session_evidences` on `session.ended`; returns immediately.
  Integration test (S7).

*DoD: a closed session's events are turned into persisted evidences asynchronously; CI green.*

### Review workload
Solo project, direct-to-`main`, one commit per subphase (M3.1 → M3.5). No PR chain.
