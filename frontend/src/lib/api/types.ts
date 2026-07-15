export type SessionResult = "passed" | "failed" | "pending";

export interface SessionSummary {
  session_id: string;
  agent_name: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  result: SessionResult;
  score_global: number | null;
}

export interface Scores {
  conversational: number | null;
  operational: number | null;
  technical: number | null;
  risk: number | null;
}

export interface BlockingFlag {
  code: string;
  reason: string;
}

export interface Report {
  report_id: string;
  session_id: string;
  score_global: number;
  scores: Scores;
  result: "passed" | "failed";
  blocking_flags: BlockingFlag[];
  generated_at: string;
}

export interface ActiveSession {
  session_id: string;
  agent_id: string;
  status: string;
  started_at: string;
  speaking_role: "agent" | "user" | null;
  last_interruption_at: string | null;
}

export interface Agent {
  agent_id: string;
  vapi_assistant_id: string;
  name: string;
  objective: string;
  description: string;
  status: string;
}

export interface RegisterAgentInput {
  vapi_assistant_id: string;
  name: string;
  objective: string;
  description?: string;
}

export interface EventOut {
  event_id: string;
  session_id: string;
  event_type: string;
  source: string;
  sequence_number: number;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface AgentResponsePayload {
  content: string;
  role: "assistant";
  turn_index: number;
}

export interface UserInputPayload {
  content: string;
  role: "user";
  turn_index: number;
}

export interface InterruptionDetectedPayload {
  [key: string]: unknown;
}

export interface SilenceInterval {
  assistant_turn_index: number;
  user_turn_index: number;
  started_at: string;
  ended_at: string;
  duration_ms: number;
}

export interface SilenceDetectedPayload {
  count: number;
  threshold_ms: number;
  detector_version: string;
  intervals: SilenceInterval[];
}

export interface TranscriptTurn {
  turnIndex: number;
  role: "assistant" | "user";
  content: string;
  timestamp: string;
  interrupted: boolean;
  silenceBeforeMs: number | null;
}
