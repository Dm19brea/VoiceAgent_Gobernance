import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ActiveSession } from "@/lib/api/types";

import { ActiveSessionsPanel } from "./ActiveSessionsPanel";

const NOW = "2026-01-01T10:00:10.000Z";

function makeSession(overrides: Partial<ActiveSession> = {}): ActiveSession {
  return {
    session_id: "call-live",
    agent_id: "a-1",
    status: "active",
    started_at: "2026-01-01T10:00:00Z",
    speaking_role: null,
    last_interruption_at: null,
    ...overrides,
  };
}

const sessions: ActiveSession[] = [makeSession()];

describe("ActiveSessionsPanel", () => {
  it("renders the active sessions", () => {
    render(<ActiveSessionsPanel sessions={sessions} />);

    expect(screen.getByText("call-live")).toBeInTheDocument();
  });

  it("shows an empty state when there are none", () => {
    render(<ActiveSessionsPanel sessions={[]} />);

    expect(screen.getByText(/no active sessions/i)).toBeInTheDocument();
  });

  describe("speaking indicator", () => {
    it('shows "Agent speaking" when speaking_role is agent', () => {
      render(<ActiveSessionsPanel sessions={[makeSession({ speaking_role: "agent" })]} />);

      expect(screen.getByText("Agent speaking")).toBeInTheDocument();
    });

    it('shows "User speaking" when speaking_role is user', () => {
      render(<ActiveSessionsPanel sessions={[makeSession({ speaking_role: "user" })]} />);

      expect(screen.getByText("User speaking")).toBeInTheDocument();
    });

    it('shows "Idle" when speaking_role is null', () => {
      render(<ActiveSessionsPanel sessions={[makeSession({ speaking_role: null })]} />);

      expect(screen.getByText("Idle")).toBeInTheDocument();
    });
  });

  describe("interruption badge", () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date(NOW));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("renders the amber badge when the interruption is within ~4s of now", () => {
      const recent = new Date(new Date(NOW).getTime() - 2000).toISOString();

      render(<ActiveSessionsPanel sessions={[makeSession({ last_interruption_at: recent })]} />);

      expect(screen.getByText("User interrupted")).toBeInTheDocument();
    });

    it("does not render the badge when the interruption is older than the window", () => {
      const stale = new Date(new Date(NOW).getTime() - 10_000).toISOString();

      render(<ActiveSessionsPanel sessions={[makeSession({ last_interruption_at: stale })]} />);

      expect(screen.queryByText("User interrupted")).not.toBeInTheDocument();
    });

    it("does not render the badge when last_interruption_at is null", () => {
      render(<ActiveSessionsPanel sessions={[makeSession({ last_interruption_at: null })]} />);

      expect(screen.queryByText("User interrupted")).not.toBeInTheDocument();
    });

    it("renders the badge when last_interruption_at is slightly in the future (clock skew)", () => {
      const skewed = new Date(new Date(NOW).getTime() + 1500).toISOString();

      render(<ActiveSessionsPanel sessions={[makeSession({ last_interruption_at: skewed })]} />);

      expect(screen.getByText("User interrupted")).toBeInTheDocument();
    });
  });
});
