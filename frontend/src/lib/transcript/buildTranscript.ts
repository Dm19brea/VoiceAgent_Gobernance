import type {
  AgentResponsePayload,
  EventOut,
  SilenceDetectedPayload,
  TranscriptTurn,
  UserInputPayload,
} from "@/lib/api/types";

const AGENT_RESPONSE = "conversation.agent_response";
const USER_INPUT = "conversation.user_input";
const INTERRUPTION_DETECTED = "conversation.interruption_detected";
const SILENCE_DETECTED = "conversation.silence_detected";

function isConversationEvent(event: EventOut): boolean {
  return event.event_type.startsWith("conversation.");
}

function sortByTimestamp(events: EventOut[]): EventOut[] {
  return [...events].sort((a, b) => {
    const timeDelta = Date.parse(a.timestamp) - Date.parse(b.timestamp);
    if (timeDelta !== 0) return timeDelta;
    const turnIndexA = (a.payload as { turn_index?: number }).turn_index ?? 0;
    const turnIndexB = (b.payload as { turn_index?: number }).turn_index ?? 0;
    return turnIndexA - turnIndexB;
  });
}

function assembleTurns(events: EventOut[]): TranscriptTurn[] {
  return sortByTimestamp(events)
    .filter((event) => event.event_type === AGENT_RESPONSE || event.event_type === USER_INPUT)
    .map((event) => {
      const payload = event.payload as unknown as AgentResponsePayload | UserInputPayload;
      return {
        turnIndex: payload.turn_index,
        role: payload.role,
        content: payload.content,
        timestamp: event.timestamp,
        interrupted: false,
        silenceBeforeMs: null,
      };
    });
}

function attachInterruptions(turns: TranscriptTurn[], events: EventOut[]): TranscriptTurn[] {
  const interruptions = events.filter((event) => event.event_type === INTERRUPTION_DETECTED);
  if (interruptions.length === 0 || turns.length === 0) return turns;

  const nextTurns = [...turns];
  for (const interruption of interruptions) {
    const interruptionTime = Date.parse(interruption.timestamp);
    // A barge-in cuts off the agent turn being spoken: the last agent turn whose
    // timestamp is at or before the interruption. Turns are already ordered by
    // timestamp, so the last matching index is the most recent agent utterance.
    // If no agent turn precedes the interruption, no turn was being spoken.
    let targetIndex = -1;
    nextTurns.forEach((turn, index) => {
      if (turn.role === "assistant" && Date.parse(turn.timestamp) <= interruptionTime) {
        targetIndex = index;
      }
    });
    const target = targetIndex >= 0 ? nextTurns[targetIndex] : undefined;
    if (target) {
      nextTurns[targetIndex] = { ...target, interrupted: true };
    }
  }
  return nextTurns;
}

function attachSilence(turns: TranscriptTurn[], events: EventOut[]): TranscriptTurn[] {
  const silenceEvents = events.filter((event) => event.event_type === SILENCE_DETECTED);
  if (silenceEvents.length === 0 || turns.length === 0) return turns;

  const silenceByUserTurnIndex = new Map<number, number>();
  for (const event of silenceEvents) {
    const payload = event.payload as unknown as SilenceDetectedPayload;
    for (const interval of payload.intervals) {
      silenceByUserTurnIndex.set(interval.user_turn_index, interval.duration_ms);
    }
  }

  return turns.map((turn) => {
    const silenceBeforeMs = silenceByUserTurnIndex.get(turn.turnIndex);
    if (silenceBeforeMs === undefined) return turn;
    return { ...turn, silenceBeforeMs };
  });
}

export function buildTranscript(events: EventOut[]): TranscriptTurn[] {
  const conversationEvents = events.filter(isConversationEvent);
  const turns = assembleTurns(conversationEvents);
  const withInterruptions = attachInterruptions(turns, conversationEvents);
  const withSilence = attachSilence(withInterruptions, conversationEvents);
  return withSilence;
}
