import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SessionSummary } from "@/lib/api/types";

import { SessionsTable } from "./SessionsTable";

const rows: SessionSummary[] = [
  {
    session_id: "call-1",
    status: "ended",
    started_at: "2026-01-01T10:00:00Z",
    ended_at: null,
    result: "passed",
    score_global: 82,
  },
];

describe("SessionsTable", () => {
  it("renders a row per session", () => {
    render(<SessionsTable sessions={rows} />);

    expect(screen.getByText("call-1")).toBeInTheDocument();
    expect(screen.getByText("passed")).toBeInTheDocument();
  });

  it("shows an empty state when there are no sessions", () => {
    render(<SessionsTable sessions={[]} />);

    expect(screen.getByText(/no sessions/i)).toBeInTheDocument();
  });
});
