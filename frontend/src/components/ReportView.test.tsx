import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { apiBaseUrl } from "@/lib/api/config";
import { server } from "@/test/msw/server";
import { renderWithQuery } from "@/test/renderWithQuery";

import { ReportView } from "./ReportView";

const reportBody = {
  report_id: "r-1",
  session_id: "call-1",
  score_global: 81.4,
  scores: { conversational: 88, operational: null, technical: 74, risk: 70 },
  result: "passed",
  blocking_flags: [],
  generated_at: "2026-01-01T10:06:00Z",
};

describe("ReportView", () => {
  it("renders the report scores on success", async () => {
    server.use(http.get(`${apiBaseUrl}/sessions/:id/report`, () => HttpResponse.json(reportBody)));

    renderWithQuery(<ReportView sessionId="call-1" />);

    expect(await screen.findByText(/81.4/)).toBeInTheDocument();
  });

  it("shows a 'not evaluated yet' state on 404", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/report`, () => new HttpResponse(null, { status: 404 })),
    );

    renderWithQuery(<ReportView sessionId="call-1" />);

    expect(await screen.findByText(/not been evaluated/i)).toBeInTheDocument();
  });

  it("shows an error state on a server error", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/report`, () => new HttpResponse(null, { status: 500 })),
    );

    renderWithQuery(<ReportView sessionId="call-1" />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
