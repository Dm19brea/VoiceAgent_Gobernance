# Operator dashboard (frontend)

Next.js (App Router) dashboard for the voice-agent governance platform. It consumes the
backend read API and the active-sessions WebSocket (milestone M6).

## Local development

```bash
npm install
npm run dev          # http://localhost:3000
```

The dashboard talks to the backend at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
Run the backend and its infra first (from the repo root and `backend/`):

```bash
docker compose up -d db redis
cd backend && uv run uvicorn src.main:app --port 8000 --reload
```

## Quality gate

```bash
npm run lint         # eslint
npm run typecheck    # tsc --noEmit
npm run test         # vitest (jsdom + RTL + MSW)
npm run build        # next build
```

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL of the backend API. The WebSocket URL is derived from it (`http`→`ws`, `https`→`wss`). | `http://localhost:8000` |
| `NEXT_PUBLIC_LOG_LEVEL` | Pino client log level (`debug`/`info`/`warn`/`error`). | `info` |

> **Build-time inlining.** `NEXT_PUBLIC_*` variables are baked into the bundle by `next build`,
> not read at runtime. `NEXT_PUBLIC_API_URL` must be set **before/at build time**, and changing it
> later requires a rebuild.

## Deployment (Railway)

This is a **second Railway service**, separate from the backend. `railway.json` (Nixpacks) builds
with `npm ci && npm run build` and serves with `npm run start` (`next start` binds Railway's
injected `$PORT` automatically). Healthcheck: `/`.

Setup:

1. Create a new Railway service from the same repo and set its **Root Directory** to `frontend`.
2. Set the service variable `NEXT_PUBLIC_API_URL=https://<backend>.up.railway.app` (needed at build
   time — see the note above).
3. On the **backend** service, set `CORS_ORIGINS=https://<frontend>.up.railway.app` so the browser
   is allowed to call the API. Multiple origins are comma-separated.

WebSockets work over Railway's proxy with no extra config: with an `https` API URL the client
connects to `wss://<backend>.up.railway.app/ws/active-sessions`.
