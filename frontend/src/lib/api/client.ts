import { getToken, setToken } from "@/lib/auth/token";

import { apiBaseUrl } from "./config";
import type { Agent, EventOut, RegisterAgentInput, Report, SessionSummary } from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Auth header for the stored dashboard token, or `{}` when signed out. */
function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { headers: authHeaders() });
  if (!response.ok) {
    throw new ApiError(response.status, `Request to ${path} failed (${response.status})`);
  }
  return (await response.json()) as T;
}

async function postJson<TBody, T>(path: string, body: TBody): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `Request to ${path} failed (${response.status})`);
  }
  return (await response.json()) as T;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

/** Logs in with the single-tenant dashboard credentials and stores the JWT. */
export async function login(username: string, password: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `Login failed (${response.status})`);
  }
  const body = (await response.json()) as TokenResponse;
  setToken(body.access_token);
}

export function getSessions(): Promise<SessionSummary[]> {
  return getJson<SessionSummary[]>("/sessions");
}

export function getAgentSessions(agentId: string): Promise<SessionSummary[]> {
  return getJson<SessionSummary[]>(`/agents/${agentId}/sessions`);
}

export function getReport(sessionId: string): Promise<Report> {
  return getJson<Report>(`/sessions/${sessionId}/report`);
}

export function getSessionEvents(sessionId: string): Promise<EventOut[]> {
  return getJson<EventOut[]>(`/sessions/${sessionId}/events`);
}

export function getAgents(): Promise<Agent[]> {
  return getJson<Agent[]>("/agents");
}

export function registerAgent(input: RegisterAgentInput): Promise<Agent> {
  return postJson<RegisterAgentInput, Agent>("/agents", input);
}

export async function deleteAgent(agentId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/agents/${agentId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `Request to /agents/${agentId} failed (${response.status})`);
  }
}
