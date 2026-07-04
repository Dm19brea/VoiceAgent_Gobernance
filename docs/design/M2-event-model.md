# M2 — Event model (SDD)

Change name: `m2-event-model` · Store: engram · Mode: interactive

## 1. Proposal

### Intent
Turn the raw Vapi webhooks (currently landing untyped in `raw_events`) into a structured
governance domain — **Agent, Session, Event** — that reconstructs a conversation as an ordered,
linked trace. This is the foundation the thesis core stands on: evidences (M3) and scoring (M4)
can only be built on a coherent event model. Without it, there is no trace to evaluate.

### Confirmed design decisions
1. **Evidence-based mapping.** Map only the Vapi message types actually observed in the real
   call — `status-update`, `assistant.started`, `speech-update`, `conversation-update`,
   `end-of-call-report` — to the closest canonical governance events. Canonical types Vapi does
   not emit are documented but not implemented (no dead code without real traffic).
2. **Session key = Vapi `call.id`.** Every Vapi webhook carries the call id; one call = one
   governance `Session`. Deterministic and robust.
3. **`raw_events` stays as the immutable landing zone.** M2 builds the `Session`/`Event` domain
   model *on top*, by transforming raw events. Preserves the faithful raw trace and the
   separation between "what was received" and "what was interpreted" (doc 3.2 immutability).

### Scope (M2.1–M2.7)
| Sub | Deliverable |
|-----|-------------|
| M2.1 | Domain entities `Agent`, `Session`, `Event` (pure, no infra) |
| M2.2 | Event taxonomy — closed vocabulary of canonical types |
| M2.3 | Vapi → canonical mapping (the real observed types) |
| M2.4 | Session lifecycle — `session.started` opens the trace; events link to their parent |
| M2.5 | Repository port (interface in `application/`) |
| M2.6 | `IngestEvent` use case — validate → normalise → link → persist |
| M2.7 | Wire the REST/Vapi adapter to the use case |

### Approach (hexagonal, inside-out)
Domain entities first (pure, TDD), then application (use case + repository port), then adapters
(Vapi mapping, persistence). The domain has zero infrastructure dependencies.

### Out of scope (deferred)
- Evidences (M3) and scoring (M4).
- Canonical event types that Vapi does not emit.
- Full agent-management UI / `POST /agents` beyond what agent association needs.

### Open question (resolve in design)
- **Agent association.** A Vapi webhook carries an `assistantId`, not our `agent_id`. Likely
  approach: register an `Agent` with its Vapi `assistantId`; on ingest, resolve
  `assistantId → agent_id`. To be settled in the design phase.

### Risks
- Real Vapi payloads are richer and messier than the spec assumed — the mapping must degrade
  gracefully on missing/unknown fields.
- Introducing `Session`/`Event` adds a new Alembic migration on top of `raw_events`.

## 2. Spec

### Requirements

- **R1 — Agent.** An `Agent` has identity (`agent_id`), descriptive fields (`name`,
  `description`, `objective`), a `status`, and a `vapi_assistant_id` used to associate incoming
  webhooks. Invariant: a valid Agent has a non-empty `name` and `objective`.
- **R2 — Session.** A `Session` is one governance session (= one Vapi call). It has a
  `session_id` (the Vapi `call.id`), belongs to an Agent, a `status` (`active`/`ended`/`failed`),
  `started_at`/`ended_at`, and counters. Invariants: opens in `active`; `started_at` set on open.
- **R3 — Event.** An `Event` is atomic and immutable: `event_id`, `session_id`, canonical
  `event_type`, `source`, `sequence_number`, `timestamp`, `payload`. Invariants:
  `sequence_number` strictly increasing within a session starting at 1; `event_type` belongs to
  the closed canonical vocabulary.
- **R4 — Canonical taxonomy.** A closed set of canonical event types (subset of doc 3.1) that M2
  can reach from the observed Vapi types. Vapi types with no mapping do **not** become domain
  Events — they remain in `raw_events` (nothing is lost). *(Design: confirm the exact subset.)*
- **R5 — Vapi → canonical mapping.** From a Vapi webhook the platform derives the `call.id`
  (session key), the canonical `event_type`, and the `source`, for each observed type:
  first webhook of a new `call.id` → `session.started`; `end-of-call-report` (or status ended) →
  `session.ended`; `speech-update`/`conversation-update` → conversation events by role.
- **R6 — Session lifecycle.** The first event of a `call.id` creates the Session (`active`) and
  emits `session.started` as sequence 1. Later events link to that Session and increment the
  sequence. A closing event sets `ended` + `ended_at`. Events for an already-ended Session are
  rejected.
- **R7 — Repository port.** The application defines an interface to persist/retrieve Sessions and
  Events, independent of SQLAlchemy.
- **R8 — `IngestEvent` use case.** Orchestrates validate → map → resolve/create Session → link
  Event (with sequence) → persist, through the port.
- **R9 — Adapter wiring.** The Vapi webhook adapter delegates to `IngestEvent`; the `raw_events`
  landing is preserved.

### Scenarios (become tests)

- **S1** Given valid data → an Agent is created with `status=active` and a `vapi_assistant_id`;
  empty `name` → invalid.
- **S2** Given a webhook with a new `call.id`, When ingested → a Session(`active`) keyed by
  `call.id` and an Event(`session.started`, seq=1) linked.
- **S3** Given an active Session, When a second webhook of the same `call.id` arrives → a new
  Event(seq=2) linked to the same Session.
- **S4** Given an active Session, When an `end-of-call-report` arrives → Session becomes `ended`,
  `ended_at` set, Event(`session.ended`) linked.
- **S5** Given an `ended` Session, When another webhook of that `call.id` arrives → the event is
  rejected (no events on a closed session).
- **S6** Given each observed Vapi type, When mapped → it yields the expected canonical
  `event_type` and `source` (one case per observed type).
- **S7** Given an unknown Vapi type, When ingested → handled gracefully (kept in `raw_events`,
  not promoted) without breaking the trace.
- **S8** Events within a session have strictly increasing sequence numbers starting at 1.

## 3. Design

### D1 — Pure domain entities, separate from persistence
Domain entities (`Agent`, `Session`, `Event`) are pure Python (dataclasses + behaviour), with
**no** SQLAlchemy/FastAPI imports (roadmap M2.1). SQLAlchemy models live in `infrastructure/`,
and a repository adapter maps domain ↔ rows. `Session` owns its invariants via behaviour:
`Session.record(event)` raises if the session is `ended`; `Session.close()` sets `ended`.

### D2 — Canonical taxonomy subset for M2 (closed enum)
Only the types reachable from real Vapi traffic:
`session.started`, `session.ended`, `conversation.agent_response`, `conversation.user_input`.
Vapi types with no mapping are **not** promoted to Events — they stay in `raw_events` (R4).
Wider taxonomy (tool.*, system.*, turn/silence/interruption) is deferred to when a source emits it.

### D3 — Vapi → canonical mapping (adapter-side)
Lives in `adapters/rest/` (provider-specific; the domain never sees Vapi). Concrete table:

| Vapi message type | Condition | Canonical `event_type` | `source` |
|---|---|---|---|
| `status-update` | `in-progress` | `session.started` | `platform` |
| `assistant.started` | — | `session.started` (dedup) | `platform` |
| `end-of-call-report` | — | `session.ended` | `platform` |
| `status-update` | ended/terminal | `session.ended` (dedup) | `platform` |
| `speech-update` / `conversation-update` | role assistant | `conversation.agent_response` | `agent` |
| `speech-update` / `conversation-update` | role user | `conversation.user_input` | `user` |
| any other | — | *(not promoted)* | — |

`session.started` / `session.ended` are **deduplicated** per session (idempotent — Vapi emits
several near the boundaries).

### D4 — Session key & lifecycle
Session key = Vapi `call.id`. The `IngestEvent` use case creates the Session **lazily** on the
first promoted event of a new `call.id` (`status=active`, `started_at` = that event's timestamp).
A `session.ended` event sets `ended` + `ended_at`. Further events for an `ended` session are
rejected (S5). Duplicate `session.started`/`session.ended` are ignored (idempotent).

### D5 — Sequence assignment
The use case assigns `sequence_number = current event count of the session + 1`. Guarantees
strictly increasing sequence starting at 1 (S8), even if webhooks arrive close together.

### D6 — Agent association (resolves the open question)
`Agent` carries `vapi_assistant_id`. On ingest, the use case extracts the assistant id from the
Vapi payload and resolves the Agent by it. **If no Agent matches, it auto-provisions a minimal
Agent** (`status=unregistered`, name derived from the assistant id) so no session is ever lost;
the operator enriches it later. Keeps the R2 invariant (every Session has an Agent).

### D7 — Repository port (`application/ports`)
A single `GovernanceRepository` interface (Protocol) decoupled from SQLAlchemy:
`get_agent_by_assistant_id`, `add_agent`, `get_session`, `add_session`, `update_session`,
`add_event`, `count_session_events`. The SQLAlchemy implementation lives in
`infrastructure/repositories/`.

### D8 — `IngestEvent` use case (`application/use_cases`)
Flow: receive a mapped command (call.id, assistant id, canonical type, source, timestamp,
payload) → resolve/auto-provision Agent → resolve/create Session → guard lifecycle → assign
sequence → build immutable `Event` → persist via the port. Tested with a **fake repository**
(no DB), per hexagonal.

### D9 — Persistence & migration
New tables `agents`, `sessions`, `events` (FKs: `sessions.agent_id → agents`,
`events.session_id → sessions`; `events.payload` JSONB; unique on `sessions.session_id`).
`raw_events` is left untouched (landing zone). One new Alembic autogenerate migration.

### D10 — Layer placement (hexagonal)
```
domain/        entities (Agent, Session, Event) + enums (EventType, Source, SessionStatus)
application/   ports (GovernanceRepository) + use_cases (IngestEvent)
infrastructure/ db models + SQLAlchemy repository
adapters/rest/ Vapi→canonical mapping + wiring (webhook delegates to IngestEvent)
```
Dependency rule holds: `adapters → application → domain`; domain imports nothing outward.

## 4. Tasks

Test-first (RED → GREEN → REFACTOR). Grouped by subphase; each group ships as one commit.

### M2.1 — Domain entities (`domain/`)
- [x] **T1** Enums `EventType` (D2 closed set), `Source`, `SessionStatus`. Test: expected members exist.
- [x] **T2** `Event` — frozen dataclass (immutable). Test: construction + immutability (R3).
- [x] **T3** `Agent` — with `vapi_assistant_id`. Test: valid; empty `name`/`objective` → error (R1, S1).
- [x] **T4** `Session` — behaviour `open()`, `record(event)` (assigns sequence, rejects if `ended`),
  `close()`. Tests: seq starts at 1 & increments (S8, D5), record after close rejected (S5),
  close sets `ended`+`ended_at` (S4).

*DoD: pure domain, 100% covered, no infra imports.*

### M2.3 — Vapi → canonical mapping (`adapters/rest/`)
- [ ] **T5** `map_vapi_event(payload)` → `(call_id, assistant_id, canonical_type|None, source,
  timestamp)`. Tests: one case per observed Vapi type + unmapped → `None` (S6, S7, D3).

### M2.5 — Repository port (`application/ports/`)
- [ ] **T6** `GovernanceRepository` Protocol (D7). Provide an in-memory **fake** for use-case tests.

### M2.6 — `IngestEvent` use case (`application/use_cases/`)
- [ ] **T7** `IngestEvent` with the fake repo. Tests: new `call.id` → Session + `session.started`
  (S2); second webhook → seq 2 (S3); `end-of-call-report` → `ended` (S4); event on ended → rejected
  (S5); unknown `assistant_id` → auto-provisioned Agent (D6). *No DB.*

### M2.7 — Persistence & wiring (`infrastructure/`, `adapters/rest/`)
- [ ] **T8** SQLAlchemy models `agents`, `sessions`, `events` (D9).
- [ ] **T9** Alembic autogenerate migration; apply to local Postgres.
- [ ] **T10** `SqlAlchemyGovernanceRepository` implementing the port. Integration test (real DB).
- [ ] **T11** Wire the Vapi webhook adapter: map → `IngestEvent`; keep `raw_events` landing.
  Integration test: Vapi-shaped payload → Session + Events persisted (R9).

*DoD: a Vapi webhook produces a linked Session/Event trace in Postgres; CI green.*

### Review workload
Solo project, direct-to-`main`, one commit per subphase (M2.1 → M2.7). No PR chain. Size grows
incrementally; each subphase is independently green.
