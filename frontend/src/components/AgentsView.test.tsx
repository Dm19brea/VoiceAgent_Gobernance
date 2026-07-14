import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { apiBaseUrl } from "@/lib/api/config";
import { server } from "@/test/msw/server";
import { renderWithQuery } from "@/test/renderWithQuery";

import { AgentsView } from "./AgentsView";

const AGENT_ONE = {
  agent_id: "a-1",
  vapi_assistant_id: "va-1",
  name: "Sales Agent",
  objective: "Book demos",
  description: "Handles inbound sales calls",
  status: "ACTIVE",
};

const AGENT_TWO = {
  agent_id: "a-2",
  vapi_assistant_id: "va-2",
  name: "Support Agent",
  objective: "Resolve tickets",
  description: "",
  status: "UNREGISTERED",
};

describe("AgentsView", () => {
  it("renders agents returned by the API", async () => {
    server.use(
      http.get(`${apiBaseUrl}/agents`, () => HttpResponse.json([AGENT_ONE, AGENT_TWO])),
    );

    renderWithQuery(<AgentsView />);

    expect(await screen.findByText("Sales Agent")).toBeInTheDocument();
    expect(screen.getByText("Support Agent")).toBeInTheDocument();
  });

  it("shows an error state when the API fails", async () => {
    server.use(http.get(`${apiBaseUrl}/agents`, () => new HttpResponse(null, { status: 500 })));

    renderWithQuery(<AgentsView />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("submits the form and refetches the list on success", async () => {
    const user = userEvent.setup();
    let listCallCount = 0;
    server.use(
      http.get(`${apiBaseUrl}/agents`, () => {
        listCallCount += 1;
        return HttpResponse.json(listCallCount === 1 ? [] : [AGENT_ONE]);
      }),
      http.post(`${apiBaseUrl}/agents`, () => HttpResponse.json(AGENT_ONE)),
    );

    renderWithQuery(<AgentsView />);

    await screen.findByText("No agents yet.");

    await user.type(screen.getByLabelText("Vapi assistant ID"), "va-1");
    await user.type(screen.getByLabelText("Name"), "Sales Agent");
    await user.type(screen.getByLabelText("Objective"), "Book demos");
    await user.click(screen.getByRole("button", { name: /save agent/i }));

    expect(await screen.findByText("Sales Agent")).toBeInTheDocument();
    expect(listCallCount).toBeGreaterThanOrEqual(2);
  });

  it("prefills the form when an existing agent row is selected for edit", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${apiBaseUrl}/agents`, () => HttpResponse.json([AGENT_ONE])));

    renderWithQuery(<AgentsView />);

    await screen.findByText("Sales Agent");
    await user.click(screen.getByRole("button", { name: /edit/i }));

    expect(screen.getByLabelText("Vapi assistant ID")).toHaveValue("va-1");
    expect(screen.getByLabelText("Name")).toHaveValue("Sales Agent");
    expect(screen.getByLabelText("Objective")).toHaveValue("Book demos");
    expect(screen.getByLabelText("Description")).toHaveValue("Handles inbound sales calls");
  });

  it("surfaces an error and keeps the entered input when the mutation fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${apiBaseUrl}/agents`, () => HttpResponse.json([])),
      http.post(`${apiBaseUrl}/agents`, () => new HttpResponse(null, { status: 422 })),
    );

    renderWithQuery(<AgentsView />);
    await screen.findByText("No agents yet.");

    await user.type(screen.getByLabelText("Vapi assistant ID"), "va-1");
    await user.type(screen.getByLabelText("Name"), "Sales Agent");
    await user.type(screen.getByLabelText("Objective"), "Book demos");
    await user.click(screen.getByRole("button", { name: /save agent/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByLabelText("Vapi assistant ID")).toHaveValue("va-1");
    expect(screen.getByLabelText("Name")).toHaveValue("Sales Agent");
    expect(screen.getByLabelText("Objective")).toHaveValue("Book demos");
  });
});
