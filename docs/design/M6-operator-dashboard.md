# M6 — Operator dashboard (SDD)

Change name: `m6-operator-dashboard` · Store: engram · Mode: interactive

## 1. Proposal

### Intent
Give the operator a minimal, well-crafted web dashboard to observe governance: browse sessions,
open a session's evaluation report with per-dimension scores (text + chart), and watch active
sessions live. It consumes the M5 read API and WebSocket. This is the milestone that makes the
platform usable by a human, not just by HTTP clients.

### Confirmed scope (user decision)
**Full M6**: M6.1 skeleton, M6.2 sessions list, M6.3 report view, M6.4 Recharts, M6.5 live
supervision (WebSocket), M6.6 Pino logging.

### Stack (doc 5.1)
Next.js (App Router) + TypeScript, TanStack Query for server state, Recharts for charts, Pino for
logging. Tests: Vitest + React Testing Library + MSW (mock the API). Lives in `frontend/` (monorepo).

### Confirmed design decisions
1. **Typed API adapter, hooks on top.** A thin typed client (`lib/api`) wraps `fetch`; TanStack
   Query hooks (`lib/queries`) own caching/loading/error. Components never call `fetch` directly.
2. **Container / presentational split.** Presentational components are pure (props in, markup out)
   and unit-tested; containers wire data via hooks. Matches the platform's clean-architecture ethos.
3. **Two small backend additions (prerequisites).** `GET /sessions` (global, paginated, most
   recent) so the dashboard has a landing list without an agent UUID; and `CORSMiddleware` so the
   browser can call the API. Both reuse existing pieces; no domain change.

### Backend prerequisites (this milestone, backend side)
| Addition | Why |
|---|---|
| `GET /sessions` global list (query port `list_sessions`) | Dashboard landing page: all recent sessions |
| `CORSMiddleware` on the FastAPI app | Browser (different origin) must be allowed to call the API |

### API consumed (M5)
`GET /sessions` (new), `GET /sessions/{id}`, `GET /sessions/{id}/report`,
`GET /agents/{id}/sessions`, `WS /ws/active-sessions`.

### Out of scope (deferred)
- Auth/login UI (backend has no auth yet).
- Agent management screens (register/edit agents).
- Historical trend across many sessions beyond a simple per-report dimension chart.
- SSR/streaming niceties; keep rendering simple (client components for data views).

### Risks
- New stack in a Python repo — isolate under `frontend/` with its own toolchain and CI job.
- Chart/live features are "deseable"; land list→report (the DoD) first, then M6.4/M6.5.
- WebSocket testing in jsdom is fiddly — cover the hook with a mocked socket, keep it thin.

## 2. Spec

### Requirements
- **R1 — Skeleton.** A Next.js (App Router, TS) app under `frontend/` with a base layout, minimal
  nav, and a configured test runner (Vitest + RTL + MSW). `NEXT_PUBLIC_API_URL` configures the API
  base. Lint (ESLint), type-check (tsc), test (Vitest) and build (next build) all pass.
- **R2 — Backend: global sessions list.** `GET /sessions` returns recent sessions
  (`SessionSummaryOut`, paginated `limit`/`offset`) via the query port. `CORSMiddleware` allows the
  dashboard origin.
- **R3 — API client + types.** A typed client exposes `getSessions`, `getSession`, `getReport`;
  TypeScript types mirror the M5 response schemas.
- **R4 — Sessions list.** The landing page fetches sessions via a TanStack Query hook and renders a
  table (session id, status, result, score, started). Loading and error states are handled.
- **R5 — Report view.** Navigating to `/sessions/{id}` fetches the report and renders global score,
  per-dimension scores, result and blocking flags. A session with no report shows a clear "not
  evaluated yet" state (the API returns 404).
- **R6 — Dimension chart.** The report view renders a Recharts chart of the four dimension scores.
- **R7 — Live supervision.** A component subscribes to `WS /ws/active-sessions` and lists the
  active sessions, updating as messages arrive; it degrades gracefully if the socket drops.
- **R8 — Logging.** A Pino logger records key client events (navigation, query errors); no secrets.
- **R9 — Quality gate.** Frontend CI job runs lint + type-check + test + build; all green.

### Scenarios (become tests)
- **S1** The layout renders the app nav/shell.
- **S2** `GET /sessions` returns recent `SessionSummaryOut` rows, paginated. (backend test)
- **S3** The sessions list renders rows from a mocked API (MSW); an empty result shows an empty state.
- **S4** The list shows an error state when the API fails.
- **S5** The report view renders global + per-dimension scores and the result from a mocked report.
- **S6** A 404 report renders a "not evaluated yet" state, not a crash.
- **S7** The dimension chart renders one bar/point per dimension given report scores.
- **S8** The live component renders active sessions pushed over a mocked WebSocket.
- **S9** The API client builds requests against `NEXT_PUBLIC_API_URL` and parses typed responses.

## 3. Design

### D1 — Project layout (`frontend/`)
```
frontend/
  src/app/            layout.tsx · page.tsx (sessions list) · sessions/[id]/page.tsx (report)
  src/components/     presentational: SessionsTable · ReportScores · DimensionChart · ActiveSessionsPanel
  src/lib/api/        client.ts (typed fetch) · types.ts (API DTOs)
  src/lib/queries/    useSessions · useReport · useActiveSessions · QueryProvider
  src/lib/logger.ts   Pino
  src/test/           setup.ts · msw handlers
```
App Router; data views are client components. TanStack Query `QueryProvider` in the root layout.

### D2 — Backend additions
- Query port `list_sessions(limit, offset) -> list[SessionSummary]`; `SqlAlchemyGovernanceQuery`
  implements it (same JOIN as `list_agent_sessions`, without the agent filter, ordered by
  `started_at` desc). Route `GET /sessions` in `query_routes.py` → `list[SessionSummaryOut]`.
- `app.add_middleware(CORSMiddleware, allow_origins=[...])` in `main.py`, origins from a setting
  (`cors_origins`, default the dev dashboard `http://localhost:3000`).

### D3 — API client + types
`lib/api/types.ts`: `SessionSummary`, `Session`, `Report` (nested `scores`), `BlockingFlag`,
`ActiveSession`. `lib/api/client.ts`: `getSessions`, `getSession`, `getReport` using `fetch` against
`NEXT_PUBLIC_API_URL`, throwing a typed error on non-2xx (404 surfaced distinctly for reports).

### D4 — Query hooks
`useSessions()`, `useReport(sessionId)`, `useActiveSessions()`. The first two wrap the client with
TanStack Query (keys, staleness). `useActiveSessions` opens a WebSocket, keeps the latest snapshot
in state, and cleans up on unmount.

### D5 — Components (presentational, tested)
`SessionsTable(rows)`, `ReportScores(report)`, `DimensionChart(scores)` (Recharts `BarChart`),
`ActiveSessionsPanel(sessions)`. Containers (route pages) call hooks and pass data down; loading /
error / empty / 404 states live in the containers.

### D6 — Logging
`lib/logger.ts` exports a Pino instance (browser-safe config). Log navigation and query errors via
a small helper; never log payloads with sensitive data.

### D7 — Tooling + CI
Vitest (jsdom) + RTL + MSW; ESLint + Prettier; `tsc --noEmit`. Frontend gate:
`npm run lint && npm run typecheck && npm run test && npm run build`. Add a `frontend` job to
`.github/workflows/ci.yml` (Node 22, `npm ci`, run the gate). Backend job unchanged.

## 4. Tasks

Test-first where there is behaviour (components/hooks/client). Scaffolding is mechanical setup with a
smoke test. Each group ships as one commit. Frontend gate per group: lint + typecheck + test + build.

### M6.1 — Skeleton + backend prerequisites
- [x] **T1** Scaffold `frontend/` (Next.js App Router, TS, ESLint/Prettier, Vitest+RTL+MSW), base
  layout + nav, smoke test (S1). Backend: `GET /sessions` global list + `CORSMiddleware` (S2).

### M6.2 — Sessions list
- [x] **T2** API client + types (S9); `useSessions`; sessions-list page with table, loading/empty/
  error states (S3, S4).

### M6.3 — Report view
- [x] **T3** `useReport`; `/sessions/[id]` page with `ReportScores`; list→detail navigation; 404
  "not evaluated" state (S5, S6).

### M6.4 — Dimension chart
- [ ] **T4** `DimensionChart` (Recharts) on the report view (S7).

### M6.5 — Live supervision
- [ ] **T5** `useActiveSessions` (WebSocket) + `ActiveSessionsPanel` (S8).

### M6.6 — Logging + CI
- [ ] **T6** Pino logger + key event logging (R8); add the `frontend` CI job (R9).

*DoD: an operator navigates from the sessions list to a session's evaluation report and sees the
scores rendered (text + chart); live active sessions are visible; frontend CI green.*

### Review workload
Solo project, direct-to-`main`, one commit per group. No PR chain.
