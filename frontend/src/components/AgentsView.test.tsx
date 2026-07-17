import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

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
  webhook_activated: true,
};

const AGENT_TWO = {
  agent_id: "a-2",
  vapi_assistant_id: "va-2",
  name: "Support Agent",
  objective: "Resolve tickets",
  description: "",
  status: "UNREGISTERED",
  webhook_activated: false,
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

  it("deletes the agent and removes the row after confirmation", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    let listCallCount = 0;
    let deleteCalledWithId: string | undefined;
    server.use(
      http.get(`${apiBaseUrl}/agents`, () => {
        listCallCount += 1;
        return HttpResponse.json(listCallCount === 1 ? [AGENT_ONE] : []);
      }),
      http.delete(`${apiBaseUrl}/agents/:id`, ({ params }) => {
        deleteCalledWithId = params.id as string;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderWithQuery(<AgentsView />);
    await screen.findByText("Sales Agent");

    await user.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(screen.queryByText("Sales Agent")).not.toBeInTheDocument());
    expect(deleteCalledWithId).toBe("a-1");
    expect(confirmSpy).toHaveBeenCalled();

    confirmSpy.mockRestore();
  });

  it("does not call delete when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    let deleteCallCount = 0;
    server.use(
      http.get(`${apiBaseUrl}/agents`, () => HttpResponse.json([AGENT_ONE])),
      http.delete(`${apiBaseUrl}/agents/:id`, () => {
        deleteCallCount += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderWithQuery(<AgentsView />);
    await screen.findByText("Sales Agent");

    await user.click(screen.getByRole("button", { name: /delete/i }));

    expect(confirmSpy).toHaveBeenCalled();
    expect(deleteCallCount).toBe(0);
    expect(screen.getByText("Sales Agent")).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("surfaces an error and keeps the row when the delete fails", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    server.use(
      http.get(`${apiBaseUrl}/agents`, () => HttpResponse.json([AGENT_ONE])),
      http.delete(`${apiBaseUrl}/agents/:id`, () => new HttpResponse(null, { status: 404 })),
    );

    renderWithQuery(<AgentsView />);
    await screen.findByText("Sales Agent");

    await user.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText("Sales Agent")).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("toggles agent activation and reflects the updated state", async () => {
    const user = userEvent.setup();
    let activateCalledWithId: string | undefined;
    let listCallCount = 0;
    server.use(
      http.get(`${apiBaseUrl}/agents`, () => {
        listCallCount += 1;
        return HttpResponse.json([
          { ...AGENT_TWO, webhook_activated: listCallCount > 1 },
        ]);
      }),
      http.post(`${apiBaseUrl}/agents/:id/activate`, ({ params }) => {
        activateCalledWithId = params.id as string;
        return HttpResponse.json({ ...AGENT_TWO, webhook_activated: true });
      }),
    );

    renderWithQuery(<AgentsView />);
    await screen.findByText("Support Agent");

    await user.click(screen.getByRole("button", { name: /^activate$/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /deactivate/i })).toBeInTheDocument());
    expect(activateCalledWithId).toBe("a-2");
  });

  it("surfaces an error when the activation toggle fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${apiBaseUrl}/agents`, () => HttpResponse.json([AGENT_TWO])),
      http.post(`${apiBaseUrl}/agents/:id/activate`, () => new HttpResponse(null, { status: 404 })),
    );

    renderWithQuery(<AgentsView />);
    await screen.findByText("Support Agent");

    await user.click(screen.getByRole("button", { name: /^activate$/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
