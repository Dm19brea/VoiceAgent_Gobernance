import { clearToken, getToken, setToken } from "@/lib/auth/token";

import { apiBaseUrl } from "./config";
import type { Agent, EventOut, RegisterAgentInput, Report, SessionSummary } from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly body?: unknown,
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

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  window.location.assign("/login");
}

let refreshInFlight: Promise<boolean> | null = null;

/** Rotates the refresh cookie for a new access token. Returns false on failure. */
async function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        if (!response.ok) return false;
        const body = (await response.json()) as { access_token: string };
        setToken(body.access_token);
        return true;
      } catch {
        return false;
      }
    })();
  }
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

async function toApiError(response: Response, path: string): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  return new ApiError(response.status, `Request to ${path} failed (${response.status})`, body);
}

/**
 * Shared fetch wrapper: attaches the bearer token, always sends
 * `credentials: "include"` (so the HttpOnly refresh cookie travels with
 * requests), and on a 401 attempts one silent `/auth/refresh` + retry before
 * giving up and redirecting to `/login`.
 */
async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    credentials: "include",
    headers: { ...authHeaders(), ...init.headers },
  });

  if (response.status !== 401) {
    return response;
  }

  const refreshed = await refreshAccessToken();
  if (!refreshed) {
    clearToken();
    redirectToLogin();
    return response;
  }

  return fetch(`${apiBaseUrl}${path}`, {
    ...init,
    credentials: "include",
    headers: { ...authHeaders(), ...init.headers },
  });
}

async function getJson<T>(path: string): Promise<T> {
  const response = await request(path);
  if (!response.ok) {
    throw await toApiError(response, path);
  }
  return (await response.json()) as T;
}

async function postJson<TBody, T>(path: string, body: TBody): Promise<T> {
  const response = await request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await toApiError(response, path);
  }
  return (await response.json()) as T;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

interface SetupResponse extends TokenResponse {
  vapi_webhook_secret: string;
}

interface AuthStatusResponse {
  needs_setup: boolean;
}

/** First-run detection: whether no dashboard credentials have been provisioned yet. */
export async function getAuthStatus(): Promise<{ needsSetup: boolean }> {
  const response = await fetch(`${apiBaseUrl}/auth/status`, { credentials: "include" });
  if (!response.ok) {
    throw await toApiError(response, "/auth/status");
  }
  const body = (await response.json()) as AuthStatusResponse;
  return { needsSetup: body.needs_setup };
}

/**
 * Provisions the first-run dashboard account. Stores the returned access
 * token and returns the webhook secret, which the API only ever shows once.
 */
export async function setupAccount(
  username: string,
  password: string,
): Promise<{ vapiWebhookSecret: string }> {
  const response = await fetch(`${apiBaseUrl}/auth/setup`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw await toApiError(response, "/auth/setup");
  }
  const body = (await response.json()) as SetupResponse;
  setToken(body.access_token);
  return { vapiWebhookSecret: body.vapi_webhook_secret };
}

/** Logs in with the single-tenant dashboard credentials and stores the JWT. */
export async function login(username: string, password: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw await toApiError(response, "/auth/login");
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
  const response = await request(`/agents/${agentId}`, { method: "DELETE" });
  if (!response.ok) {
    throw await toApiError(response, `/agents/${agentId}`);
  }
}

export async function activateAgent(agentId: string): Promise<Agent> {
  const path = `/agents/${agentId}/activate`;
  const response = await request(path, { method: "POST" });
  if (!response.ok) {
    throw await toApiError(response, path);
  }
  return (await response.json()) as Agent;
}

export async function deactivateAgent(agentId: string): Promise<Agent> {
  const path = `/agents/${agentId}/deactivate`;
  const response = await request(path, { method: "POST" });
  if (!response.ok) {
    throw await toApiError(response, path);
  }
  return (await response.json()) as Agent;
}
