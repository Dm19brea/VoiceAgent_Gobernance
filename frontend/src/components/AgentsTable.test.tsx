import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import type { Agent } from "@/lib/api/types";

import { AgentsTable } from "./AgentsTable";

const agents: Agent[] = [
  {
    agent_id: "agent-1",
    vapi_assistant_id: "vapi-1",
    name: "Citas",
    objective: "Schedule appointments",
    description: "",
    status: "active",
    webhook_activated: true,
  },
];

function renderTable(overrides: Partial<ComponentProps<typeof AgentsTable>> = {}) {
  return render(
    <AgentsTable
      agents={agents}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      deletingAgentId={null}
      onToggleActivation={vi.fn()}
      togglingAgentId={null}
      {...overrides}
    />,
  );
}

describe("AgentsTable", () => {
  it("renders a row per agent", () => {
    renderTable();

    expect(screen.getByText("Citas")).toBeInTheDocument();
  });

  it("shows an empty state when there are no agents", () => {
    render(
      <AgentsTable
        agents={[]}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        deletingAgentId={null}
        onToggleActivation={vi.fn()}
        togglingAgentId={null}
      />,
    );

    expect(screen.getByText(/no agents/i)).toBeInTheDocument();
  });

  it("wraps the status value in a StatusBadge", () => {
    renderTable();

    const badge = screen.getByText("active");
    expect(badge).toHaveAttribute("data-testid", "status-badge");
  });

  it("falls back to a neutral StatusBadge variant for an unmapped status", () => {
    const inactiveAgents: Agent[] = [{ ...agents[0], agent_id: "agent-2", status: "inactive" }];
    renderTable({ agents: inactiveAgents });

    const badge = screen.getByText("inactive");
    expect(badge.className).not.toContain("success");
    expect(badge.className).not.toContain("danger");
  });

  it("renders an Activated header and shows the activation state per agent", () => {
    renderTable();

    expect(screen.getByText("Activated")).toBeInTheDocument();
    expect(screen.getByText("activated")).toBeInTheDocument();
  });

  it("shows a deactivated state for an agent whose webhook credentials are off", () => {
    const inactiveAgents: Agent[] = [{ ...agents[0], webhook_activated: false }];
    renderTable({ agents: inactiveAgents });

    expect(screen.getByText("deactivated")).toBeInTheDocument();
  });

  it("calls onToggleActivation with the agent when the toggle button is clicked", async () => {
    const user = userEvent.setup();
    const onToggleActivation = vi.fn();
    renderTable({ onToggleActivation });

    await user.click(screen.getByRole("button", { name: /deactivate/i }));

    expect(onToggleActivation).toHaveBeenCalledWith(agents[0]);
  });

  it("disables the toggle and shows a spinner for the agent being toggled", () => {
    renderTable({ togglingAgentId: "agent-1" });

    const toggleButton = screen.getByRole("button", { name: /deactivate/i });
    expect(toggleButton).toBeDisabled();
    expect(screen.getByTestId("spinner")).toBeInTheDocument();
  });

  it("shows an Activate label for a deactivated agent", () => {
    const inactiveAgents: Agent[] = [{ ...agents[0], webhook_activated: false }];
    renderTable({ agents: inactiveAgents });

    expect(screen.getByRole("button", { name: /^activate$/i })).toBeInTheDocument();
  });
});
