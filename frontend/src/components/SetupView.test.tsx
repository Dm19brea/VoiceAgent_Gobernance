import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiBaseUrl } from "@/lib/api/config";
import { clearToken, getToken } from "@/lib/auth/token";
import { server } from "@/test/msw/server";

import { SetupView } from "./SetupView";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

describe("SetupView", () => {
  afterEach(() => {
    clearToken();
    replace.mockClear();
  });

  it("shows live password rule feedback as the user types", async () => {
    const user = userEvent.setup();
    render(<SetupView />);

    expect(screen.getByText(/at least 12 characters/i)).toHaveAttribute(
      "data-satisfied",
      "false",
    );

    await user.type(screen.getByLabelText(/^password$/i), "Correct-Horse9!");

    expect(screen.getByText(/at least 12 characters/i)).toHaveAttribute(
      "data-satisfied",
      "true",
    );
  });

  it("disables submit while the password violates the policy", async () => {
    const user = userEvent.setup();
    render(<SetupView />);

    await user.type(screen.getByLabelText(/username/i), "admin");
    await user.type(screen.getByLabelText(/^password$/i), "weak");

    expect(screen.getByRole("button", { name: /create account/i })).toBeDisabled();
  });

  it("provisions the account and surfaces the webhook secret once on success", async () => {
    server.use(
      http.post(`${apiBaseUrl}/auth/setup`, () =>
        HttpResponse.json({
          access_token: "setup-token",
          token_type: "bearer",
          vapi_webhook_secret: "whsec_abc123",
        }),
      ),
    );
    const user = userEvent.setup();
    render(<SetupView />);

    await user.type(screen.getByLabelText(/username/i), "admin");
    await user.type(screen.getByLabelText(/^password$/i), "Correct-Horse9!");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(getToken()).toBe("setup-token"));
    expect(await screen.findByText("whsec_abc123")).toBeInTheDocument();
    expect(screen.getAllByText(/vapi/i).length).toBeGreaterThan(0);
    expect(replace).not.toHaveBeenCalled();
  });

  it("lets the user continue into the app after acknowledging the secret", async () => {
    server.use(
      http.post(`${apiBaseUrl}/auth/setup`, () =>
        HttpResponse.json({
          access_token: "setup-token",
          token_type: "bearer",
          vapi_webhook_secret: "whsec_abc123",
        }),
      ),
    );
    const user = userEvent.setup();
    render(<SetupView />);

    await user.type(screen.getByLabelText(/username/i), "admin");
    await user.type(screen.getByLabelText(/^password$/i), "Correct-Horse9!");
    await user.click(screen.getByRole("button", { name: /create account/i }));
    await screen.findByText("whsec_abc123");

    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(replace).toHaveBeenCalledWith("/");
  });

  it("shows an error and stores no token when the account already exists", async () => {
    server.use(http.post(`${apiBaseUrl}/auth/setup`, () => new HttpResponse(null, { status: 409 })));
    const user = userEvent.setup();
    render(<SetupView />);

    await user.type(screen.getByLabelText(/username/i), "admin");
    await user.type(screen.getByLabelText(/^password$/i), "Correct-Horse9!");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/already/i);
    expect(getToken()).toBeNull();
  });
});
