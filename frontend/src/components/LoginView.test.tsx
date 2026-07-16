import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiBaseUrl } from "@/lib/api/config";
import { clearToken, getToken } from "@/lib/auth/token";
import { server } from "@/test/msw/server";

import { LoginView } from "./LoginView";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

describe("LoginView", () => {
  afterEach(() => clearToken());

  it("logs in and stores the token on correct credentials", async () => {
    server.use(
      http.post(`${apiBaseUrl}/auth/login`, () =>
        HttpResponse.json({ access_token: "test-token", token_type: "bearer" }),
      ),
    );
    const user = userEvent.setup();

    render(<LoginView />);
    await user.type(screen.getByLabelText(/username/i), "admin");
    await user.type(screen.getByLabelText(/password/i), "correct-horse");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => expect(getToken()).toBe("test-token"));
  });

  it("shows an error message on incorrect credentials", async () => {
    server.use(
      http.post(`${apiBaseUrl}/auth/login`, () => new HttpResponse(null, { status: 401 })),
    );
    const user = userEvent.setup();

    render(<LoginView />);
    await user.type(screen.getByLabelText(/username/i), "admin");
    await user.type(screen.getByLabelText(/password/i), "wrong");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid/i);
    expect(getToken()).toBeNull();
  });
});
