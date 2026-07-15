import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
            agent_name: "Citas",
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

  it("filters sessions by agent when one is selected", async () => {
    server.use(
      http.get(`${apiBaseUrl}/agents`, () =>
        HttpResponse.json([
          {
            agent_id: "a1",
            vapi_assistant_id: "va-1",
            name: "Ventas",
            objective: "Vender",
            description: "",
            status: "ACTIVE",
          },
        ]),
      ),
      http.get(`${apiBaseUrl}/sessions`, () =>
        HttpResponse.json([
          {
            session_id: "call-all",
            agent_name: "Citas",
            status: "ended",
            started_at: "2026-01-01T10:00:00Z",
            ended_at: null,
            result: "passed",
            score_global: 90,
          },
        ]),
      ),
      http.get(`${apiBaseUrl}/agents/a1/sessions`, () =>
        HttpResponse.json([
          {
            session_id: "call-ventas",
            agent_name: "Ventas",
            status: "ended",
            started_at: "2026-01-01T10:00:00Z",
            ended_at: null,
            result: "passed",
            score_global: 90,
          },
        ]),
      ),
    );

    const user = userEvent.setup();
    renderWithQuery(<SessionsView />);

    expect(await screen.findByText("call-all")).toBeInTheDocument();
    await screen.findByRole("option", { name: "Ventas" });

    await user.selectOptions(screen.getByRole("combobox"), "a1");

    expect(await screen.findByText("call-ventas")).toBeInTheDocument();
    expect(screen.queryByText("call-all")).not.toBeInTheDocument();
  });

  it("reverts to all sessions when All is selected again", async () => {
    server.use(
      http.get(`${apiBaseUrl}/agents`, () =>
        HttpResponse.json([
          {
            agent_id: "a1",
            vapi_assistant_id: "va-1",
            name: "Ventas",
            objective: "Vender",
            description: "",
            status: "ACTIVE",
          },
        ]),
      ),
      http.get(`${apiBaseUrl}/sessions`, () =>
        HttpResponse.json([
          {
            session_id: "call-all",
            agent_name: "Citas",
            status: "ended",
            started_at: "2026-01-01T10:00:00Z",
            ended_at: null,
            result: "passed",
            score_global: 90,
          },
        ]),
      ),
      http.get(`${apiBaseUrl}/agents/a1/sessions`, () =>
        HttpResponse.json([
          {
            session_id: "call-ventas",
            agent_name: "Ventas",
            status: "ended",
            started_at: "2026-01-01T10:00:00Z",
            ended_at: null,
            result: "passed",
            score_global: 90,
          },
        ]),
      ),
    );

    const user = userEvent.setup();
    renderWithQuery(<SessionsView />);

    await screen.findByRole("option", { name: "Ventas" });
    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "a1");
    expect(await screen.findByText("call-ventas")).toBeInTheDocument();

    await user.selectOptions(select, "");

    expect(await screen.findByText("call-all")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText("call-ventas")).not.toBeInTheDocument();
    });
  });

  it("shows the empty state when the filtered agent has no sessions", async () => {
    server.use(
      http.get(`${apiBaseUrl}/agents`, () =>
        HttpResponse.json([
          {
            agent_id: "a2",
            vapi_assistant_id: "va-2",
            name: "Nuevo",
            objective: "Nada",
            description: "",
            status: "ACTIVE",
          },
        ]),
      ),
      http.get(`${apiBaseUrl}/sessions`, () => HttpResponse.json([])),
      http.get(`${apiBaseUrl}/agents/a2/sessions`, () => HttpResponse.json([])),
    );

    const user = userEvent.setup();
    renderWithQuery(<SessionsView />);

    await screen.findByRole("option", { name: "Nuevo" });
    await user.selectOptions(screen.getByRole("combobox"), "a2");

    expect(await screen.findByText(/no sessions/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
