import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import {
  deleteAgent,
  getAgentSessions,
  getAgents,
  getReport,
  getSessions,
  login,
  registerAgent,
} from "@/lib/api/client";
import { apiBaseUrl } from "@/lib/api/config";
import { clearToken, getToken, setToken } from "@/lib/auth/token";
import { server } from "@/test/msw/server";

afterEach(() => {
  clearToken();
});

describe("getSessions", () => {
  it("fetches and returns typed sessions from the API", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions`, () =>
        HttpResponse.json([
          {
            session_id: "call-1",
            agent_name: "Citas",
            status: "ended",
            started_at: "2026-01-01T10:00:00Z",
            ended_at: null,
            result: "passed",
            score_global: 82,
          },
        ]),
      ),
    );

    const sessions = await getSessions();

    expect(sessions).toHaveLength(1);
    expect(sessions[0].session_id).toBe("call-1");
    expect(sessions[0].result).toBe("passed");
    expect(sessions[0].score_global).toBe(82);
  });

  it("throws on a non-2xx response", async () => {
    server.use(http.get(`${apiBaseUrl}/sessions`, () => new HttpResponse(null, { status: 500 })));

    await expect(getSessions()).rejects.toThrow();
  });
});

describe("getAgentSessions", () => {
  it("fetches and returns typed sessions scoped to an agent", async () => {
    server.use(
      http.get(`${apiBaseUrl}/agents/:agentId/sessions`, () =>
        HttpResponse.json([
          {
            session_id: "call-2",
            agent_name: "Ventas",
            status: "ended",
            started_at: "2026-01-01T10:00:00Z",
            ended_at: null,
            result: "passed",
            score_global: 82,
          },
        ]),
      ),
    );

    const sessions = await getAgentSessions("a-1");

    expect(sessions).toHaveLength(1);
    expect(sessions[0].session_id).toBe("call-2");
    expect(sessions[0].agent_name).toBe("Ventas");
  });

  it("throws on a non-2xx response", async () => {
    server.use(
      http.get(`${apiBaseUrl}/agents/:agentId/sessions`, () => new HttpResponse(null, { status: 500 })),
    );

    await expect(getAgentSessions("a-1")).rejects.toThrow();
  });
});

describe("getReport", () => {
  it("fetches a session's evaluation report", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/report`, () =>
        HttpResponse.json({
          report_id: "r-1",
          session_id: "call-1",
          score_global: 81.4,
          scores: { conversational: 88, operational: null, technical: 74, risk: 70 },
          result: "passed",
          blocking_flags: [],
          generated_at: "2026-01-01T10:06:00Z",
        }),
      ),
    );

    const report = await getReport("call-1");

    expect(report.score_global).toBe(81.4);
    expect(report.scores.technical).toBe(74);
    expect(report.result).toBe("passed");
  });

  it("throws an ApiError with status 404 when the report is absent", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/report`, () => new HttpResponse(null, { status: 404 })),
    );

    await expect(getReport("call-x")).rejects.toMatchObject({ status: 404 });
  });
});

describe("getAgents", () => {
  it("fetches and returns typed agents from the API", async () => {
    server.use(
      http.get(`${apiBaseUrl}/agents`, () =>
        HttpResponse.json([
          {
            agent_id: "a-1",
            vapi_assistant_id: "va-1",
            name: "Sales Agent",
            objective: "Book demos",
            description: "",
            status: "ACTIVE",
          },
        ]),
      ),
    );

    const agents = await getAgents();

    expect(agents).toHaveLength(1);
    expect(agents[0].agent_id).toBe("a-1");
    expect(agents[0].status).toBe("ACTIVE");
  });

  it("throws on a non-2xx response", async () => {
    server.use(http.get(`${apiBaseUrl}/agents`, () => new HttpResponse(null, { status: 500 })));

    await expect(getAgents()).rejects.toThrow();
  });
});

describe("registerAgent", () => {
  it("posts the agent payload and returns the persisted agent", async () => {
    let receivedBody: unknown;
    server.use(
      http.post(`${apiBaseUrl}/agents`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json({
          agent_id: "a-2",
          vapi_assistant_id: "va-2",
          name: "Support Agent",
          objective: "Resolve tickets",
          description: "",
          status: "ACTIVE",
        });
      }),
    );

    const agent = await registerAgent({
      vapi_assistant_id: "va-2",
      name: "Support Agent",
      objective: "Resolve tickets",
    });

    expect(agent.agent_id).toBe("a-2");
    expect(receivedBody).toMatchObject({
      vapi_assistant_id: "va-2",
      name: "Support Agent",
      objective: "Resolve tickets",
    });
  });

  it("throws an ApiError with status 422 on invalid input", async () => {
    server.use(http.post(`${apiBaseUrl}/agents`, () => new HttpResponse(null, { status: 422 })));

    await expect(
      registerAgent({ vapi_assistant_id: "", name: "", objective: "" }),
    ).rejects.toMatchObject({ status: 422 });
  });
});

describe("deleteAgent", () => {
  it("sends a DELETE request to the agent's endpoint and resolves on 204", async () => {
    let receivedMethod: string | undefined;
    server.use(
      http.delete(`${apiBaseUrl}/agents/:id`, ({ request }) => {
        receivedMethod = request.method;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await expect(deleteAgent("a-1")).resolves.toBeUndefined();
    expect(receivedMethod).toBe("DELETE");
  });

  it("throws an ApiError with status 404 when the agent is absent", async () => {
    server.use(http.delete(`${apiBaseUrl}/agents/:id`, () => new HttpResponse(null, { status: 404 })));

    await expect(deleteAgent("missing")).rejects.toMatchObject({ status: 404 });
  });
});

describe("login", () => {
  it("stores the returned token on success", async () => {
    server.use(
      http.post(`${apiBaseUrl}/auth/login`, async ({ request }) => {
        const body = (await request.json()) as { username: string; password: string };
        expect(body).toMatchObject({ username: "admin", password: "correct-horse" });
        return HttpResponse.json({ access_token: "fake-jwt-token", token_type: "bearer" });
      }),
    );

    await login("admin", "correct-horse");

    expect(getToken()).toBe("fake-jwt-token");
  });

  it("throws an ApiError with status 401 on wrong credentials and stores no token", async () => {
    server.use(
      http.post(`${apiBaseUrl}/auth/login`, () => new HttpResponse(null, { status: 401 })),
    );

    await expect(login("admin", "wrong")).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBeNull();
  });
});

describe("authenticated requests", () => {
  it("attaches the stored token as a Bearer Authorization header", async () => {
    setToken("stored-token");
    let receivedAuth: string | null = null;
    server.use(
      http.get(`${apiBaseUrl}/sessions`, ({ request }) => {
        receivedAuth = request.headers.get("Authorization");
        return HttpResponse.json([]);
      }),
    );

    await getSessions();

    expect(receivedAuth).toBe("Bearer stored-token");
  });

  it("sends no Authorization header when no token is stored", async () => {
    let receivedAuth: string | null = "unset";
    server.use(
      http.get(`${apiBaseUrl}/sessions`, ({ request }) => {
        receivedAuth = request.headers.get("Authorization");
        return HttpResponse.json([]);
      }),
    );

    await getSessions();

    expect(receivedAuth).toBeNull();
  });
});
