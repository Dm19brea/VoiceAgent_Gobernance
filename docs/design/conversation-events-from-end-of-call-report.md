# Deriving conversation.* canonical events from end-of-call-report

> **Status: SETTLED.** All open questions resolved (see [Open questions](#open-questions-iterating)).
> The conversational storage model is locked and ready to feed the SDD change.

## Goal

Rework how conversational canonical events are stored for the governance system.
`conversation-update` will be **removed** as an event source (kept only as raw
landing). This document defines whether — and how — each `conversation.*` event
from [`vapi-event-coverage.md`](./vapi-event-coverage.md) can instead be derived
from the **`end-of-call-report`** webhook at session close.

Scope: **only the `conversation.*` events.** Session and system events are out of
scope here.

## What the end-of-call-report actually contains

At the end of a call, `message.artifact` carries three views of the same dialogue:

| Field | Shape | Use |
|---|---|---|
| `messagesOpenAIFormatted` | `[{role: "user"\|"assistant", content}]` | consolidated, deduplicated turns |
| `messages` | `[{role: "bot"\|"user", message, time, endTime, duration, secondsFromStart, metadata}]` | turns **with timing** |
| `transcript` | plain `AI:/User:` text | full transcript for NLU / judge |

It also carries `analysis.summary`, `analysis.successEvaluation` (Vapi's own
goal verdict), a `scorecard`, and `performanceMetrics.turnLatencies`.

**Critical gap:** the report has **no explicit interruption marker**. The `messages`
entries contain timing but no `interrupted: true` field.

## Per-event derivation verdict

| Event | Derivable from end-of-call-report? | Source within the report | Notes |
|---|---|---|---|
| `conversation.agent_response` | ✅ Yes, clean | `messagesOpenAIFormatted` role=assistant | primary content event |
| `conversation.user_input` | ✅ Yes, clean | `messagesOpenAIFormatted` role=user | primary content event |
| `conversation.turn_started` | ✅ Yes (post-terminal) | `messages[].time` / `secondsFromStart` | timing only available at close |
| `conversation.turn_ended` | ✅ Yes (post-terminal) | `messages[].endTime` | timing only available at close |
| `conversation.interruption_detected` | ❌ **No** | — (no interruption flag in report) | must stay real-time (`user-interrupted`) |
| `conversation.silence_detected` (implementado) | ✅ Derivable | gap between consecutive `endTime` → next `time` | compute inter-turn silence from timestamps |
| `conversation.topic_change` (pending) | ⚠️ Only with NLU | `transcript` + new analysis | needs segmentation logic |
| `conversation.goal_achieved` / `goal_failed` (pending) | ✅ Derivable | `analysis.successEvaluation` or own LLM judge over `transcript` | see Option C / LLM-judge design |

## The interruption exception

`conversation.interruption_detected` is the **only** `conversation.*` event that
cannot be sourced from the `end-of-call-report`. The report exposes only
timestamps; there is no explicit "user interrupted here" signal. Inferring it from
timing overlap (user `time` earlier than the bot's `endTime`) is **fragile and
approximate**, not an authoritative governance record.

The clean, explicit source is the real-time **`user-interrupted`** webhook —
already ingested and already mapped to `conversation.interruption_detected` in
`backend/src/adapters/rest/vapi_mapping.py`. This is the same webhook feeding the
[real-time speaking indicator](./real-time-speaking-indicator.md), so the two
designs are consistent.

**Confirmed:** `user-interrupted` does reach the webhook in real time when an
interruption actually occurs. It is absent from the sample call
(`019f4cc4-…`) only because the user never interrupted the agent in that call —
not because the webhook is unsubscribed.

**Consequence:** `interruption_detected` is the one `conversation.*` event that
**crosses** both paths (real-time + persistence). It cannot be purely
post-terminal.

## Proposed storage model (to be confirmed)

| Event | Proposed canonical source |
|---|---|
| `agent_response`, `user_input` | derived at close from `end-of-call-report` (Option C, appended) |
| `turn_started`, `turn_ended` | **not persisted** — live-only signal from `speech-update`; turn timing is attached to the content events instead |
| `interruption_detected` | real-time `user-interrupted` |
| `silence_detected` | derived at close from report timing gaps |
| `topic_change` | out of scope (needs NLU) |
| `goal_achieved` / `goal_failed` | out of scope here (LLM judge / `successEvaluation`) |
| `conversation-update` | **removed** — raw landing only, no canonical events |

## Open questions (iterating)

- ✅ RESOLVED **turn_started / turn_ended — live-only, NOT persisted.**
  Decision: option (b). They carry no auditable fact that is not already on the
  content events (`agent_response` / `user_input` already carry the per-turn timing
  from the report). Persisting them would duplicate information, double the event
  volume, and widen the `sequence_number` collision surface. They remain a
  **live-only ephemeral signal** driven by `speech-update` for the speaking
  indicator; turn timing is attached to the content events for the audit record.
  Rationale for the TFM: promote to canonical only what carries auditable meaning
  not already captured elsewhere — turn boundaries are temporal metadata, not an
  independent auditable fact.

- ✅ RESUELTO **silence_detected — implementado (ya no está diferido).**
  Esta sección quedó desactualizada: el evento `conversation.silence_detected` está
  implementado de extremo a extremo. El backend lo deriva de los huecos de timing
  del `end-of-call-report` (`backend/src/adapters/rest/vapi_mapping.py` /
  `tasks.py`), persistiendo un único evento por sesión con
  `payload.intervals[]` (uno por hueco de silencio detectado, sin umbral mínimo
  de duración). El frontend consume `GET /sessions/{id}/events`, arma la
  transcripción con `buildTranscript` (`frontend/src/lib/transcript/buildTranscript.ts`)
  y renderiza un divisor de silencio por intervalo en `TranscriptView`
  (`frontend/src/components/TranscriptView.tsx`) con el formato
  `── ⏸ {duración}s de silencio ──`. La decisión original de "diferir hasta
  definir el umbral de negocio" quedó superada: la implementación actual no
  aplica umbral — se muestra cualquier hueco de silencio detectado — dejando la
  eventual afinación de umbral como una mejora futura, no como trabajo
  pendiente bloqueante.

- ✅ RESOLVED **Ordering / sequence at close — C1 (append-only).**
  With turns no longer persisted, the only real-time-sourced conversational event
  is `interruption_detected` (persisted during the call, low `sequence_number`),
  while `agent_response` / `user_input` are derived and **appended at close**, so
  they land after the in-call events (potentially after `session.ended`) by
  `sequence_number`. C2 (reordering/inserting between already-written events) would
  risk the per-session uniqueness invariant that previously broke the deploy.
  Decision: **C1**, with explicit field semantics —
  - `sequence_number` = ingestion / provenance order (monotonic per session, no
    collisions).
  - `timestamp` = true chronological order (each content event carries it from the
    report's `messages[].time`).

  Consumers that need the real timeline **order by `timestamp`**, not by
  `sequence_number`.

- ✅ RESOLVED **`speech-update` is live-only**, not a canonical event source. It
  feeds the speaking indicator only (consequence of the turn decision above).

## Related

- [`real-time-speaking-indicator.md`](./real-time-speaking-indicator.md) — live-view
  design using `speech-update` + `user-interrupted`.
- [`vapi-event-coverage.md`](./vapi-event-coverage.md) — canonical event taxonomy.
