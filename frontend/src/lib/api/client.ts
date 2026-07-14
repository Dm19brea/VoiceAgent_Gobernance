import { apiBaseUrl } from "./config";
import type { Agent, RegisterAgentInput, Report, SessionSummary } from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`);
  if (!response.ok) {
    throw new ApiError(response.status, `Request to ${path} failed (${response.status})`);
  }
  return (await response.json()) as T;
}

async function postJson<TBody, T>(path: string, body: TBody): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `Request to ${path} failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function getSessions(): Promise<SessionSummary[]> {
  return getJson<SessionSummary[]>("/sessions");
}

export function getReport(sessionId: string): Promise<Report> {
  return getJson<Report>(`/sessions/${sessionId}/report`);
}

export function getAgents(): Promise<Agent[]> {
  return getJson<Agent[]>("/agents");
}

export function registerAgent(input: RegisterAgentInput): Promise<Agent> {
  return postJson<RegisterAgentInput, Agent>("/agents", input);
}
