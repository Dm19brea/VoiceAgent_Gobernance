import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the raw status text so getByText(status) still matches", () => {
    render(<StatusBadge status="passed" />);

    const badge = screen.getByText("passed");
    expect(badge).toHaveAttribute("data-testid", "status-badge");
  });

  it("applies a success variant class for passed", () => {
    render(<StatusBadge status="passed" />);

    expect(screen.getByTestId("status-badge").className).toContain("success");
  });

  it("applies a danger variant class for failed", () => {
    render(<StatusBadge status="failed" />);

    expect(screen.getByTestId("status-badge").className).toContain("danger");
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("falls back to a neutral variant for unmapped statuses", () => {
    render(<StatusBadge status="ended" />);

    const badge = screen.getByTestId("status-badge");
    expect(badge.className).not.toContain("success");
    expect(badge.className).not.toContain("danger");
    expect(screen.getByText("ended")).toBeInTheDocument();
  });
});
