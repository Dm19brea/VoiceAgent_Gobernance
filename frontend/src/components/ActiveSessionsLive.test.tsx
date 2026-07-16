import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth/token";

import { ActiveSessionsLive } from "./ActiveSessionsLive";

class MockWebSocket {
  static last: MockWebSocket | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  readyState = 1;

  constructor(readonly url: string) {
    MockWebSocket.last = this;
  }

  close(): void {}

  emit(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

describe("ActiveSessionsLive", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    clearToken();
  });

  it("renders active sessions pushed over the socket", () => {
    vi.stubGlobal("WebSocket", MockWebSocket);

    render(<ActiveSessionsLive />);
    act(() => {
      MockWebSocket.last?.emit([
        {
          session_id: "call-live",
          agent_id: "a-1",
          status: "active",
          started_at: "2026-01-01T10:00:00Z",
        },
      ]);
    });

    expect(screen.getByText("call-live")).toBeInTheDocument();
  });

  it("appends the stored auth token as a WS query param", () => {
    setToken("ws-test-token");
    vi.stubGlobal("WebSocket", MockWebSocket);

    render(<ActiveSessionsLive />);

    expect(MockWebSocket.last?.url).toContain("?token=ws-test-token");
  });
});
