export type SessionResult = "passed" | "failed" | "pending";

export interface SessionSummary {
  session_id: string;
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
