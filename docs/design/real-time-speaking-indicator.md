# Real-time speaking indicator for the live session view

## Goal

Today the live monitoring view only shows whether a session is **active or closed**.
This design upgrades it to show, **in real time while the call is happening**:

- Who is currently speaking: **the agent** or **the user**.
- When **the user interrupted the agent**.

This is a deliberate scope shift ("360° pivot"): the platform stops being a
purely post-mortem governance store for the live surface and gains a real-time
conversational-state channel, while post-terminal governance stays authoritative
(see [Scope boundary](#scope-boundary-real-time-vs-post-terminal)).

## Which Vapi webhook to use — and why

The correct source is **`speech-update`**, not `conversation-update`. The two are
frequently confused because both arrive many times during a call, but they answer
different questions.

### `speech-update` — speaking state (the right tool)

Each `speech-update` webhook carries, at the root of `message`:

```json
{
  "type": "speech-update",
  "role": "assistant",   // or "user"
  "status": "started",   // or "stopped"
  "turn": 0
}
```

It answers **"role X just STARTED / STOPPED speaking"**. It is an event about the
*speaking state* of one party, emitted once per start and once per stop. This maps
directly onto a live "who is talking now" indicator.

### `conversation-update` — cumulative content snapshot (the wrong tool)

`conversation-update` has **no root-level `role` or `status`**. Its `message`
carries a cumulative array (`conversation` / `messages` / `messagesOpenAIFormatted`)
holding the entire transcript so far, re-sent and grown by one entry each time.

It answers **"here is the whole conversation up to now"**, i.e. accumulated
*content*, not *speaking state*. It cannot tell you who is speaking at this instant,
so it is unsuitable for the live indicator. It is also cumulative and mutable, which
makes it a poor source for discrete governance events as well.

### Interruption is a third, separate webhook

The interruption signal comes from neither of the above. Vapi emits a dedicated
**`user-interrupted`** webhook, already mapped to
`conversation.interruption_detected` in
`backend/src/adapters/rest/vapi_mapping.py` (`_resolve`, `user-interrupted` branch).
The platform already ingests it; the remaining work is surfacing it to the front end.

## Live state model

Drive the indicator as a small state machine fed by the two real-time webhooks:

| Incoming webhook | Live UI effect |
|---|---|
| `speech-update` `{role: assistant, status: started}` | Agent is speaking |
| `speech-update` `{role: assistant, status: stopped}` | Clear agent indicator |
| `speech-update` `{role: user, status: started}` | User is speaking |
| `speech-update` `{role: user, status: stopped}` | Clear user indicator |
| `user-interrupted` | Flash "user interrupted the agent" |

Suggested live snapshot shape (conceptual, not final field names):

```
speakingRole: "assistant" | "user" | null
lastInterruptionAt: timestamp | null
```

## Architecture

The live view is served from the active-session store (Redis) and pushed to the
browser over the WebSocket channel.

1. **Ingestion** — `speech-update` and `user-interrupted` land raw first (immutable
   landing, unchanged), then flow through the existing webhook handler
   (`backend/src/adapters/rest/vapi.py`).
2. **Active state** — extend the active-session snapshot with the speaking-state
   fields above, and update them inside the active-state update path
   (`update_active_state`) when a `speech-update` / `user-interrupted` arrives.
3. **Push** — emit the updated snapshot over the WebSocket (`backend/src/adapters/rest/ws.py`)
   so the front end reflects the speaking indicator without polling.

Everything is still landed raw regardless; only the promotion to a real-time
signal is new.

## Scope boundary: real-time vs post-terminal

This design covers **only** the real-time live surface. It is intentionally
separate from the post-terminal governance/content path:

| Concern | Source |
|---|---|
| Real-time live-view (who is speaking, interruption) | `speech-update` + `user-interrupted` |
| Post-terminal governance, transcript content, goal evaluation (LLM judge) | `end-of-call-report.artifact.messagesOpenAIFormatted` |
| Everything else | Raw landing only |

`conversation-update` is **not** promoted to canonical events in either path; it is
kept as raw landing only (provenance/audit that it was received).

## Rationale for the TFM

- **Governance principle preserved**: every Vapi payload is still landed raw
  first; only signals with clear meaning are promoted.
- **`speech-update` earns its place**: it provides live speaking state that the
  post-mortem `end-of-call-report` cannot (the report is only available once the
  call ends).
- **`conversation-update` remains dead weight**: its content is fully superseded
  by the `end-of-call-report`, and its cumulative/mutable shape makes it a poor
  source for either real-time or discrete governance events.

## Open items / next steps

- Confirm `speech-update` and `user-interrupted` are subscribed in the assistant's
  **serverMessages** (not only clientMessages) so they actually reach the webhook.
- Decide final snapshot field names and WebSocket message contract.
- Decide whether the live speaking-state transitions should also be persisted as
  canonical events or remain live-only (governance value vs. noise).
