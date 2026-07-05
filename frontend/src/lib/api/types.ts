export type SessionResult = "passed" | "failed" | "pending";

export interface SessionSummary {
  session_id: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  result: SessionResult;
  score_global: number | null;
}
