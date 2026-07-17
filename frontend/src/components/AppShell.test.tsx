import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";

let pathname = "/";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
}));

describe("AppShell", () => {
  afterEach(() => {
    pathname = "/";
  });

  it("renders the main nav and its content", () => {
    render(
      <AppShell>
        <p>page content</p>
      </AppShell>,
    );

    expect(screen.getByRole("navigation", { name: /main/i })).toBeInTheDocument();
    expect(screen.getByText("Governance")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sessions/i })).toBeInTheDocument();
    expect(screen.getByText("page content")).toBeInTheDocument();
  });

  it("marks the Sessions link as the current page when on /", () => {
    pathname = "/";

    render(
      <AppShell>
        <p>page content</p>
      </AppShell>,
    );

    expect(screen.getByRole("link", { name: /sessions/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: /agents/i })).not.toHaveAttribute("aria-current");
  });

  it("marks the Agents link as the current page when on /agents", () => {
    pathname = "/agents";

    render(
      <AppShell>
        <p>page content</p>
      </AppShell>,
    );

    expect(screen.getByRole("link", { name: /agents/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: /sessions/i })).not.toHaveAttribute("aria-current");
  });
});
