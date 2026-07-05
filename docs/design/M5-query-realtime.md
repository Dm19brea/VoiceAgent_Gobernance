# M5 — Query API + real-time supervision (SDD)

Change name: `m5-query-realtime` · Store: engram · Mode: interactive

## 1. Proposal

### Intent
Expose everything built in M0–M4 through the API: a read side (CQRS-light) that serves the
governance data (sessions, events, evidences, evaluation reports) per the doc 4.4 contract, plus
real-time supervision of active sessions via Redis + WebSocket. This is the milestone that makes
the platform observable from the outside and unblocks the M6 dashboard.

### Confirmed scope (user decision)
**Full M5**: read API (M5.1–M5.3, M5.6) **and** real-time (M5.4 Redis active state + M5.5 WebSocket).

### Confirmed design decisions
1. **CQRS-light.** A dedicated read port (`GovernanceQuery`) separate from the write
   `GovernanceRepository`. Reads return projections shaped for the API, never leaking SQLAlchemy.
2. **4.4 contract is authoritative.** Endpoint shapes follow doc 4.4 §4.4.3 Grupo 3, not the
   looser roadmap shorthand (`GET /sessions`, `/reports`, `/metrics`). "Metrics" are served inside
   the report (scores + metrics snapshot), which is where the 4.4 contract places them.
3. **Real-time is a peripheral adapter.** Active-session state lives in Redis (fast, ephemeral),
   written best-effort during ingestion so a Redis failure never breaks event ingestion. The
   WebSocket is a thin adapter that reads that state — the domain is untouched.

### Read surface (doc 4.4 §4.4.3, Grupo 3)
| Endpoint | Purpose |
|---|---|
| `GET /sessions/{session_id}` | Session state + turn counters |
| `GET /sessions/{session_id}/events` | Full event trace (filters: `event_type`, `source`) |
| `GET /sessions/{session_id}/evidences` | Evidences built for the session |
| `GET /sessions/{session_id}/report` | Evaluation report; `404` if not evaluated yet |
| `GET /agents/{agent_id}/sessions` | List an agent's sessions + results (filter `result`, paginate) |

### Out of scope (deferred)
- `GET /agents/{agent_id}/validation` (doc 3.5.2 multi-session validation) — its own milestone.
- Auth/`401` (doc 4.4.5) — not yet modelled; deferred.
- Per-agent configurable weights, historical replay adapter.

### Risks
- WebSocket/Redis add moving parts; keep the WS adapter thin and the Redis write best-effort.
- Async WS testing is fiddly — cover it with one focused connect/receive test.

## 2. Spec

### Requirements
- **R1 — Query port (CQRS-light).** An application read interface `GovernanceQuery` exposes
  session, events, evidences, report reads and an agent-session listing. It is distinct from the
  write repository and returns domain entities / read DTOs, never SQLAlchemy models.
- **R2 — Session view.** `GET /sessions/{id}` returns status, `started_at`, `ended_at` and turn
  counters (`total_turns`, `agent_turns`, `user_turns`). `404` if the session does not exist.
- **R3 — Events view.** `GET /sessions/{id}/events` returns the trace ordered by
  `sequence_number`, optionally filtered by `event_type` and/or `source`.
- **R4 — Evidences view.** `GET /sessions/{id}/evidences` returns the session's evidences.
- **R5 — Report view.** `GET /sessions/{id}/report` returns the report shaped per doc 4.4
  (`report_id`, `session_id`, `score_global`, nested `scores` object, `result`, `blocking_flags`,
  `generated_at`). `404` if no report exists yet.
- **R6 — Agent sessions listing.** `GET /agents/{agent_id}/sessions` lists the agent's sessions
  with `result` (`passed`/`failed`/`pending` when unevaluated) and `score_global` (nullable),
  filterable by `result`, paginated by `limit`/`offset`.
- **R7 — Active-session store.** A port stores a snapshot of each active session and lists the
  active ones. A Redis adapter implements it. Ingestion marks a session active on `session.started`
  and ended on `session.ended`, **best-effort** (a Redis failure must not break ingestion).
- **R8 — WebSocket supervision.** A `GET /ws/active-sessions` WebSocket sends the current active
  sessions on connect (reading the store) and pushes updates periodically.
- **R9 — OpenAPI contract.** The generated OpenAPI schema (`/openapi.json`) exposes every read path
  above, reflecting the doc 4.4 contract in `/docs`.
- **R10 — Read side is pure read.** Query endpoints never mutate state.

### Scenarios (become tests)
- **S1** The query adapter returns a session with its events; unknown session → `None`.
- **S2** `GET /sessions/{id}` → `200` with counters; unknown → `404`.
- **S3** `GET /sessions/{id}/events?source=agent` returns only agent events, ordered.
- **S4** `GET /sessions/{id}/evidences` returns the persisted evidences.
- **S5** `GET /sessions/{id}/report` → `200` with nested `scores`; a session without a report → `404`.
- **S6** `GET /agents/{id}/sessions?result=passed` lists only passed sessions; unevaluated ones
  report `result="pending"`; `limit`/`offset` paginate.
- **S7** The Redis store: `mark_active` then `list_active` returns the snapshot; `mark_ended`
  removes it.
- **S8** Ingesting `session.started` marks the session active; `session.ended` marks it ended
  (verified through the store).
- **S9** A Redis failure during ingestion does not fail the request (best-effort).
- **S10** Connecting to `/ws/active-sessions` yields a first message listing active sessions.
- **S11** `/openapi.json` contains the five read paths with a `GET` method.

## 3. Design

### D1 — Query port (application, M5.1)
`application/ports/query.py`: `GovernanceQuery` Protocol (async) +
`SessionSummary` read DTO (`session_id`, `agent_id`, `status`, `started_at`, `ended_at`,
`result`, `score_global`). Methods:
`get_session`, `get_events(session_id, event_type=None, source=None)`, `get_evidences`,
`get_report`, `list_agent_sessions(agent_id, result=None, limit=50, offset=0)`.

### D2 — Query adapter (infrastructure)
`infrastructure/repositories/governance_query.py`: `SqlAlchemyGovernanceQuery`. Reuses the write
repository's reads for `get_session`/`get_evidences`/`get_report` (DRY over the existing mapping);
adds `get_events` (filtered `select` ordered by `sequence_number`) and `list_agent_sessions`
(LEFT JOIN `sessions` → `evaluation_reports`, mapping to `SessionSummary`, `result="pending"` when
no report).

### D3 — REST response schemas + routes (M5.2–M5.3)
`adapters/rest/query_schemas.py`: `SessionOut`, `SessionSummaryOut`, `ReportOut` (nested
`scores`), `EvidenceOut`, `EventOut` (Pydantic). `adapters/rest/query_routes.py`: a router wiring
each endpoint through `Depends(get_session)` → `SqlAlchemyGovernanceQuery` → map to Out schema.
`404` via `HTTPException` when a session/report is absent. Turn counters computed from the loaded
session's events. Registered in `main.py`.

### D4 — Active-session store (M5.4)
`application/ports/active_sessions.py`: `ActiveSessionStore` Protocol +
`ActiveSessionSnapshot` DTO (`session_id`, `agent_id`, `status`, `started_at`). Methods
`mark_active(snapshot)`, `mark_ended(session_id)`, `list_active()`.
`infrastructure/redis/active_sessions.py`: `RedisActiveSessionStore` backed by a Redis hash
(`HSET`/`HDEL`/`HGETALL`, JSON-encoded snapshots) using `redis.asyncio` on `settings.redis_url`.
Wired into the Vapi webhook (and event ingest): on `session.started` → `mark_active`, on
`session.ended` → `mark_ended`, wrapped best-effort like the Celery enqueue (R7, R9→S9).

### D5 — WebSocket adapter (M5.5)
`adapters/rest/ws.py`: `@router.websocket("/ws/active-sessions")`. On connect: `accept`, read
`list_active` from the store, send it as JSON. Then loop: sleep an interval, re-send the current
snapshot, until the client disconnects (`WebSocketDisconnect`). Thin; no domain logic.

### D6 — OpenAPI verification (M5.6)
Routes carry `tags`/`summary` so `/docs` is readable. A test asserts `/openapi.json` exposes the
five read paths (R9/S11).

### D7 — Layer placement
```
application/   ports/query.py (GovernanceQuery + SessionSummary) · ports/active_sessions.py (ActiveSessionStore + ActiveSessionSnapshot)
infrastructure/ repositories/governance_query.py · redis/active_sessions.py
adapters/rest/ query_schemas.py · query_routes.py · ws.py · (webhook writes active state)
```
Dependency rule holds: query/real-time are read/peripheral adapters; the domain is untouched.

## 4. Tasks

Test-first (RED → GREEN → REFACTOR). Grouped by area; each group ships as one commit.
Verification gate per group: `pytest` + `ruff check` + `ruff format --check` + `mypy`.

### M5.1 — Query port + read adapter
- [x] **T1** `GovernanceQuery` Protocol + `SessionSummary` DTO; `SqlAlchemyGovernanceQuery`
  (`get_session`, `get_events` filtered, `get_evidences`, `get_report`, `list_agent_sessions`
  join + pagination). Integration tests (S1, S6).

### M5.2 — Session detail + agent listing endpoints
- [x] **T2** `SessionOut`/`SessionSummaryOut` schemas + routes `GET /sessions/{id}` and
  `GET /agents/{id}/sessions`. Client tests (S2, S6).

### M5.3 — Report, evidences, events endpoints
- [x] **T3** `ReportOut` (nested `scores`)/`EvidenceOut`/`EventOut` + routes
  `GET /sessions/{id}/report` (404 if none), `/evidences`, `/events` (filters). Client tests
  (S3, S4, S5).

### M5.4 — Redis active-session state
- [x] **T4** `ActiveSessionStore` port + `ActiveSessionSnapshot` DTO + `RedisActiveSessionStore`;
  wire best-effort into ingestion. Tests: store round-trip (S7), ingestion marks state (S8),
  Redis failure is swallowed (S9).

### M5.5 — WebSocket supervision
- [x] **T5** `/ws/active-sessions` adapter reading the store. Connect/receive test (S10).

### M5.6 — OpenAPI verification
- [ ] **T6** Route tags/summaries + test asserting the read paths in `/openapi.json` (S11).

*DoD: the doc 4.4 read contract is served and documented; active sessions are observable live over
WebSocket; CI green (pytest + ruff + mypy).*

### Review workload
Solo project, direct-to-`main`, one commit per group. No PR chain.
