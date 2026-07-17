import { render, screen } from "@testing-library/react";
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
  },
];

describe("AgentsTable", () => {
  it("renders a row per agent", () => {
    render(
      <AgentsTable agents={agents} onEdit={vi.fn()} onDelete={vi.fn()} deletingAgentId={null} />,
    );

    expect(screen.getByText("Citas")).toBeInTheDocument();
  });

  it("shows an empty state when there are no agents", () => {
    render(<AgentsTable agents={[]} onEdit={vi.fn()} onDelete={vi.fn()} deletingAgentId={null} />);

    expect(screen.getByText(/no agents/i)).toBeInTheDocument();
  });

  it("wraps the status value in a StatusBadge", () => {
    render(
      <AgentsTable agents={agents} onEdit={vi.fn()} onDelete={vi.fn()} deletingAgentId={null} />,
    );

    const badge = screen.getByText("active");
    expect(badge).toHaveAttribute("data-testid", "status-badge");
  });

  it("falls back to a neutral StatusBadge variant for an unmapped status", () => {
    const inactiveAgents: Agent[] = [{ ...agents[0], agent_id: "agent-2", status: "inactive" }];
    render(
      <AgentsTable
        agents={inactiveAgents}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        deletingAgentId={null}
      />,
    );

    const badge = screen.getByText("inactive");
    expect(badge.className).not.toContain("success");
    expect(badge.className).not.toContain("danger");
  });
});
