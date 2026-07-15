import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { apiBaseUrl } from "@/lib/api/config";
import { server } from "@/test/msw/server";
import { renderWithQuery } from "@/test/renderWithQuery";

import { TranscriptView } from "./TranscriptView";

const baseTimestamp = "2026-01-01T10:00:00.000Z";

function isoOffset(seconds: number): string {
  return new Date(Date.parse(baseTimestamp) + seconds * 1000).toISOString();
}

const turnEvents = [
  {
    event_id: "e-1",
    session_id: "call-1",
    event_type: "conversation.agent_response",
    source: "agent",
    sequence_number: 1,
    timestamp: isoOffset(0),
    payload: { content: "Hola, ¿en qué puedo ayudarte?", role: "assistant", turn_index: 0 },
  },
  {
    event_id: "e-2",
    session_id: "call-1",
    event_type: "conversation.user_input",
    source: "user",
    sequence_number: 2,
    timestamp: isoOffset(5),
    payload: { content: "Quiero información sobre mi cuenta", role: "user", turn_index: 1 },
  },
];

const interruptionEvent = {
  event_id: "e-3",
  session_id: "call-1",
  event_type: "conversation.interruption_detected",
  source: "user",
  sequence_number: 3,
  timestamp: isoOffset(0.1),
  payload: {},
};

const silenceEvent = {
  event_id: "e-4",
  session_id: "call-1",
  event_type: "conversation.silence_detected",
  source: "system",
  sequence_number: 4,
  timestamp: isoOffset(6),
  payload: {
    count: 1,
    threshold_ms: 300,
    detector_version: "v1",
    intervals: [
      {
        assistant_turn_index: 0,
        user_turn_index: 1,
        started_at: isoOffset(1),
        ended_at: isoOffset(4.2),
        duration_ms: 3200,
      },
    ],
  },
};

describe("TranscriptView", () => {
  it("shows a loading indicator while the request is in flight", () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/events`, async () => {
        await new Promise(() => {});
        return HttpResponse.json([]);
      }),
    );

    renderWithQuery(<TranscriptView sessionId="call-1" />);

    expect(screen.getByText(/Cargando transcripción/)).toBeInTheDocument();
  });

  it("shows an empty/pending message when there are no conversation turns", async () => {
    server.use(http.get(`${apiBaseUrl}/sessions/:id/events`, () => HttpResponse.json([])));

    renderWithQuery(<TranscriptView sessionId="call-1" />);

    expect(
      await screen.findByText(/Esta sesión aún no tiene transcripción procesada\./),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error state when the events request fails", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/events`, () => new HttpResponse(null, { status: 500 })),
    );

    renderWithQuery(<TranscriptView sessionId="call-1" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/No se pudo cargar la transcripción\./);
  });

  it("renders turn bubbles in order with role labels", async () => {
    server.use(http.get(`${apiBaseUrl}/sessions/:id/events`, () => HttpResponse.json(turnEvents)));

    renderWithQuery(<TranscriptView sessionId="call-1" />);

    const first = await screen.findByText(/Hola, ¿en qué puedo ayudarte\?/);
    const second = await screen.findByText(/Quiero información sobre mi cuenta/);
    expect(first).toBeInTheDocument();
    expect(second).toBeInTheDocument();

    const bubbles = screen.getAllByTestId("transcript-turn");
    expect(bubbles).toHaveLength(2);
    expect(bubbles[0]).toHaveTextContent(/Hola, ¿en qué puedo ayudarte\?/);
    expect(bubbles[1]).toHaveTextContent(/Quiero información sobre mi cuenta/);
  });

  it("renders a distinguishable interruption indicator without altering content", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/events`, () =>
        HttpResponse.json([...turnEvents, interruptionEvent]),
      ),
    );

    renderWithQuery(<TranscriptView sessionId="call-1" />);

    const bubbles = await screen.findAllByTestId("transcript-turn");
    expect(bubbles).toHaveLength(2);
    expect(bubbles[0]).toHaveTextContent(/Hola, ¿en qué puedo ayudarte\?/);
    expect(screen.getByTestId("interruption-indicator")).toBeInTheDocument();
  });

  it("renders a silence divider before the turn it precedes", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/events`, () =>
        HttpResponse.json([...turnEvents, silenceEvent]),
      ),
    );

    renderWithQuery(<TranscriptView sessionId="call-1" />);

    expect(await screen.findByText("── ⏸ 3.2s de silencio ──")).toBeInTheDocument();
  });
});
