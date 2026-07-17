import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiBaseUrl } from "@/lib/api/config";
import { clearToken, setToken } from "@/lib/auth/token";
import { server } from "@/test/msw/server";

import { AuthGate } from "./AuthGate";

const replace = vi.fn();
let pathname = "/";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
}));

describe("AuthGate", () => {
  afterEach(() => {
    clearToken();
    replace.mockClear();
    pathname = "/";
  });

  it("redirects to /setup when needs_setup is true and no token is stored", async () => {
    server.use(
      http.get(`${apiBaseUrl}/auth/status`, () => HttpResponse.json({ needs_setup: true })),
    );

    render(
      <AuthGate>
        <p>dashboard content</p>
      </AuthGate>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/setup"));
    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
  });

  it("redirects to /login when needs_setup is false and no token is stored", async () => {
    server.use(
      http.get(`${apiBaseUrl}/auth/status`, () => HttpResponse.json({ needs_setup: false })),
    );

    render(
      <AuthGate>
        <p>dashboard content</p>
      </AuthGate>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
  });

  it("renders children without redirecting when a token is already stored", async () => {
    setToken("valid-token");

    render(
      <AuthGate>
        <p>dashboard content</p>
      </AuthGate>,
    );

    expect(await screen.findByText("dashboard content")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("renders children on /login without calling /auth/status", async () => {
    pathname = "/login";
    let statusCalls = 0;
    server.use(
      http.get(`${apiBaseUrl}/auth/status`, () => {
        statusCalls += 1;
        return HttpResponse.json({ needs_setup: false });
      }),
    );

    render(
      <AuthGate>
        <p>login page</p>
      </AuthGate>,
    );

    expect(await screen.findByText("login page")).toBeInTheDocument();
    expect(statusCalls).toBe(0);
    expect(replace).not.toHaveBeenCalled();
  });

  it("renders children on /setup without calling /auth/status", async () => {
    pathname = "/setup";
    let statusCalls = 0;
    server.use(
      http.get(`${apiBaseUrl}/auth/status`, () => {
        statusCalls += 1;
        return HttpResponse.json({ needs_setup: true });
      }),
    );

    render(
      <AuthGate>
        <p>setup page</p>
      </AuthGate>,
    );

    expect(await screen.findByText("setup page")).toBeInTheDocument();
    expect(statusCalls).toBe(0);
    expect(replace).not.toHaveBeenCalled();
  });
});
