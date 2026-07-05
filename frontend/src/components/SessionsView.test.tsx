import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { apiBaseUrl } from "@/lib/api/config";
import { server } from "@/test/msw/server";
import { renderWithQuery } from "@/test/renderWithQuery";

import { SessionsView } from "./SessionsView";

describe("SessionsView", () => {
  it("renders sessions returned by the API", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions`, () =>
        HttpResponse.json([
          {
            session_id: "call-9",
            status: "ended",
            started_at: "2026-01-01T10:00:00Z",
            ended_at: null,
            result: "failed",
            score_global: 40,
          },
        ]),
      ),
    );

    renderWithQuery(<SessionsView />);

    expect(await screen.findByText("call-9")).toBeInTheDocument();
  });

  it("shows an error state when the API fails", async () => {
    server.use(http.get(`${apiBaseUrl}/sessions`, () => new HttpResponse(null, { status: 500 })));

    renderWithQuery(<SessionsView />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
