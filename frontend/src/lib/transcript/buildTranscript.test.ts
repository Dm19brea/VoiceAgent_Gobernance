import { describe, expect, it } from "vitest";

import type { EventOut } from "@/lib/api/types";

import { buildTranscript } from "./buildTranscript";

function userInput(turnIndex: number, timestamp: string, sequenceNumber: number): EventOut {
  return {
    event_id: `user-${turnIndex}`,
    session_id: "s-1",
    event_type: "conversation.user_input",
    source: "user",
    sequence_number: sequenceNumber,
    timestamp,
    payload: { content: `user says ${turnIndex}`, role: "user", turn_index: turnIndex },
  };
}

function agentResponse(turnIndex: number, timestamp: string, sequenceNumber: number): EventOut {
  return {
    event_id: `agent-${turnIndex}`,
    session_id: "s-1",
    event_type: "conversation.agent_response",
    source: "agent",
    sequence_number: sequenceNumber,
    timestamp,
    payload: { content: `agent says ${turnIndex}`, role: "assistant", turn_index: turnIndex },
  };
}

function interruption(timestamp: string, sequenceNumber: number): EventOut {
  return {
    event_id: `interruption-${sequenceNumber}`,
    session_id: "s-1",
    event_type: "conversation.interruption_detected",
    source: "user",
    sequence_number: sequenceNumber,
    timestamp,
    payload: {},
  };
}

function silenceDetected(
  intervals: Array<{
    assistant_turn_index: number;
    user_turn_index: number;
    started_at: string;
    ended_at: string;
    duration_ms: number;
  }>,
  sequenceNumber: number,
): EventOut {
  return {
    event_id: `silence-${sequenceNumber}`,
    session_id: "s-1",
    event_type: "conversation.silence_detected",
    source: "system",
    sequence_number: sequenceNumber,
    timestamp: intervals[0]?.ended_at ?? "2026-01-01T10:00:00Z",
    payload: {
      count: intervals.length,
      threshold_ms: 300,
      detector_version: "v1",
      intervals,
    },
  };
}

describe("buildTranscript", () => {
  it("orders turns strictly by timestamp, ignoring non-monotonic sequence_number", () => {
    // sequence_number is reversed relative to timestamp order
    const events: EventOut[] = [
      userInput(0, "2026-01-01T10:00:00Z", 5),
      agentResponse(1, "2026-01-01T10:00:05Z", 1),
    ];

    const turns = buildTranscript(events);

    expect(turns.map((t) => t.turnIndex)).toEqual([0, 1]);
    expect(turns.map((t) => t.timestamp)).toEqual([
      "2026-01-01T10:00:00Z",
      "2026-01-01T10:00:05Z",
    ]);
  });

  it("assembles alternating user/agent turns in order with correct role labels", () => {
    const events: EventOut[] = [
      userInput(0, "2026-01-01T10:00:00Z", 1),
      agentResponse(1, "2026-01-01T10:00:05Z", 2),
      userInput(2, "2026-01-01T10:00:10Z", 3),
      agentResponse(3, "2026-01-01T10:00:15Z", 4),
    ];

    const turns = buildTranscript(events);

    expect(turns).toHaveLength(4);
    expect(turns.map((t) => t.role)).toEqual(["user", "assistant", "user", "assistant"]);
    expect(turns.map((t) => t.turnIndex)).toEqual([0, 1, 2, 3]);
  });

  it("renders a turn with only the available content when the counterpart event is missing", () => {
    const events: EventOut[] = [userInput(0, "2026-01-01T10:00:00Z", 1)];

    expect(() => buildTranscript(events)).not.toThrow();
    const turns = buildTranscript(events);

    expect(turns).toHaveLength(1);
    expect(turns[0]?.role).toBe("user");
    expect(turns[0]?.content).toBe("user says 0");
  });

  it("marks the agent turn being spoken (the last agent turn at or before the interruption), not a later turn", () => {
    // Realistic barge-in: the agent is speaking (turn 0), the user interrupts,
    // then the user's words and the agent's next reply follow.
    const events: EventOut[] = [
      agentResponse(0, "2026-01-01T10:00:00Z", 1),
      interruption("2026-01-01T10:00:02Z", 2),
      userInput(1, "2026-01-01T10:00:03Z", 3),
      agentResponse(2, "2026-01-01T10:00:05Z", 4),
    ];

    const turns = buildTranscript(events);

    expect(turns.map((t) => t.turnIndex)).toEqual([0, 1, 2]);
    expect(turns.map((t) => t.content)).toEqual([
      "agent says 0",
      "user says 1",
      "agent says 2",
    ]);
    // The interrupted turn is the agent that was talking when barged in (turn 0),
    // never the user turn nor the agent's later reply.
    expect(turns[0]?.interrupted).toBe(true);
    expect(turns[1]?.interrupted).toBe(false);
    expect(turns[2]?.interrupted).toBe(false);
  });

  it("marks no turn as interrupted when no agent turn precedes the interruption", () => {
    const events: EventOut[] = [
      userInput(0, "2026-01-01T10:00:00Z", 1),
      interruption("2026-01-01T10:00:01Z", 2),
      agentResponse(1, "2026-01-01T10:00:05Z", 3),
    ];

    const turns = buildTranscript(events);

    expect(turns.every((t) => t.interrupted === false)).toBe(true);
  });

  it("marks no turn as interrupted when there are zero interruption events", () => {
    const events: EventOut[] = [
      userInput(0, "2026-01-01T10:00:00Z", 1),
      agentResponse(1, "2026-01-01T10:00:05Z", 2),
    ];

    const turns = buildTranscript(events);

    expect(turns.every((t) => t.interrupted === false)).toBe(true);
  });

  it("produces correct silenceBeforeMs for each of multiple silence intervals, matched by user_turn_index", () => {
    const events: EventOut[] = [
      agentResponse(0, "2026-01-01T10:00:00Z", 1),
      userInput(1, "2026-01-01T10:00:02Z", 2),
      agentResponse(2, "2026-01-01T10:00:03Z", 3),
      userInput(3, "2026-01-01T10:00:07Z", 4),
      agentResponse(4, "2026-01-01T10:00:08Z", 5),
      userInput(5, "2026-01-01T10:00:12Z", 6),
      silenceDetected(
        [
          {
            assistant_turn_index: 0,
            user_turn_index: 1,
            started_at: "2026-01-01T10:00:00Z",
            ended_at: "2026-01-01T10:00:02Z",
            duration_ms: 2000,
          },
          {
            assistant_turn_index: 2,
            user_turn_index: 3,
            started_at: "2026-01-01T10:00:03Z",
            ended_at: "2026-01-01T10:00:07Z",
            duration_ms: 4000,
          },
          {
            assistant_turn_index: 4,
            user_turn_index: 5,
            started_at: "2026-01-01T10:00:08Z",
            ended_at: "2026-01-01T10:00:12Z",
            duration_ms: 4000,
          },
        ],
        7,
      ),
    ];

    const turns = buildTranscript(events);

    const byTurnIndex = new Map(turns.map((t) => [t.turnIndex, t]));
    expect(byTurnIndex.get(1)?.silenceBeforeMs).toBe(2000);
    expect(byTurnIndex.get(3)?.silenceBeforeMs).toBe(4000);
    expect(byTurnIndex.get(5)?.silenceBeforeMs).toBe(4000);
    expect(byTurnIndex.get(0)?.silenceBeforeMs).toBeNull();
    expect(byTurnIndex.get(2)?.silenceBeforeMs).toBeNull();
    expect(byTurnIndex.get(4)?.silenceBeforeMs).toBeNull();
  });

  it("produces a non-null silenceBeforeMs for a sub-second interval (no minimum threshold)", () => {
    const events: EventOut[] = [
      agentResponse(0, "2026-01-01T10:00:00Z", 1),
      userInput(1, "2026-01-01T10:00:00.4Z", 2),
      silenceDetected(
        [
          {
            assistant_turn_index: 0,
            user_turn_index: 1,
            started_at: "2026-01-01T10:00:00Z",
            ended_at: "2026-01-01T10:00:00.4Z",
            duration_ms: 400,
          },
        ],
        3,
      ),
    ];

    const turns = buildTranscript(events);

    const userTurn = turns.find((t) => t.turnIndex === 1);
    expect(userTurn?.silenceBeforeMs).toBe(400);
  });

  it("returns an empty TranscriptTurn[] for an empty events input", () => {
    expect(buildTranscript([])).toEqual([]);
  });

  it("does not throw and leaves turns unaffected when a silence interval references a turn_index with no matching turn", () => {
    const events: EventOut[] = [
      agentResponse(0, "2026-01-01T10:00:00Z", 1),
      userInput(1, "2026-01-01T10:00:02Z", 2),
      silenceDetected(
        [
          {
            assistant_turn_index: 0,
            user_turn_index: 99,
            started_at: "2026-01-01T10:00:00Z",
            ended_at: "2026-01-01T10:00:02Z",
            duration_ms: 2000,
          },
        ],
        3,
      ),
    ];

    expect(() => buildTranscript(events)).not.toThrow();
    const turns = buildTranscript(events);

    expect(turns).toHaveLength(2);
    expect(turns.every((t) => t.silenceBeforeMs === null)).toBe(true);
  });
});
