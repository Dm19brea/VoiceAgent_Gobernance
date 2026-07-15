import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ReportView } from "@/components/ReportView";
import { TranscriptView } from "@/components/TranscriptView";
import { apiBaseUrl } from "@/lib/api/config";
import { server } from "@/test/msw/server";
import { renderWithQuery } from "@/test/renderWithQuery";

// Mirrors how the session detail page composes TranscriptView and ReportView
// side by side, without pulling in the async server-component page itself.
function SessionDetailFixture({ sessionId }: Readonly<{ sessionId: string }>) {
  return (
    <>
      <TranscriptView sessionId={sessionId} />
      <ReportView sessionId={sessionId} />
    </>
  );
}

describe("session detail composition", () => {
  it("keeps ReportView functional when the transcript fetch fails", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/events`, () => new HttpResponse(null, { status: 500 })),
      http.get(`${apiBaseUrl}/sessions/:id/report`, () => new HttpResponse(null, { status: 404 })),
    );

    renderWithQuery(<SessionDetailFixture sessionId="call-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/No se pudo cargar la transcripción\./);
    expect(await screen.findByText(/not been evaluated/i)).toBeInTheDocument();
  });

  it("keeps TranscriptView functional when the report fetch fails", async () => {
    server.use(
      http.get(`${apiBaseUrl}/sessions/:id/events`, () => HttpResponse.json([])),
      http.get(`${apiBaseUrl}/sessions/:id/report`, () => new HttpResponse(null, { status: 500 })),
    );

    renderWithQuery(<SessionDetailFixture sessionId="call-1" />);

    expect(
      await screen.findByText(/Esta sesión aún no tiene transcripción procesada\./),
    ).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Couldn't load the report\./);
  });
});
