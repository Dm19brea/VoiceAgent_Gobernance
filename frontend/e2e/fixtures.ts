import type { Agent, EventOut, Report, SessionSummary } from "../src/lib/api/types";

export const fixtureSessionId = "session-e2e-001";

export const fixtureAgents: Agent[] = [
  {
    agent_id: "agent-e2e-001",
    vapi_assistant_id: "vapi-e2e-001",
    name: "E2E operator agent",
    objective: "Exercise report navigation",
    description: "Deterministic Playwright fixture",
    status: "active",
  },
];

export const fixtureSessions: SessionSummary[] = [
  {
    session_id: fixtureSessionId,
    agent_name: fixtureAgents[0].name,
    status: "completed",
    started_at: "2026-07-16T10:00:00Z",
    ended_at: "2026-07-16T10:05:00Z",
    result: "passed",
    score_global: 92,
  },
];

export const fixtureEvents: EventOut[] = [];

export const fixtureReport: Report = {
  report_id: "report-e2e-001",
  session_id: fixtureSessionId,
  score_global: 92,
  scores: { conversational: 92, operational: 92, technical: 92, risk: 92 },
  result: "passed",
  blocking_flags: [],
  generated_at: "2026-07-16T10:05:00Z",
};
