import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ActiveSession } from "@/lib/api/types";

import { ActiveSessionsPanel } from "./ActiveSessionsPanel";

const sessions: ActiveSession[] = [
  {
    session_id: "call-live",
    agent_id: "a-1",
    status: "active",
    started_at: "2026-01-01T10:00:00Z",
  },
];

describe("ActiveSessionsPanel", () => {
  it("renders the active sessions", () => {
    render(<ActiveSessionsPanel sessions={sessions} />);

    expect(screen.getByText("call-live")).toBeInTheDocument();
  });

  it("shows an empty state when there are none", () => {
    render(<ActiveSessionsPanel sessions={[]} />);

    expect(screen.getByText(/no active sessions/i)).toBeInTheDocument();
  });
});
