import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { getSessions } from "@/lib/api/client";
import { apiBaseUrl } from "@/lib/api/config";
import { server } from "@/test/msw/server";

describe("getSessions", () => {
  it("fetches and returns typed sessions from the API", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions`, () =>
        HttpResponse.json([
          {
            session_id: "call-1",
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
