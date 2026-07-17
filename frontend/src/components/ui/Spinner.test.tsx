import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Spinner } from "./Spinner";

describe("Spinner", () => {
  it("renders a status role with aria-busy and default label", () => {
    render(<Spinner />);

    const spinner = screen.getByRole("status");
    expect(spinner).toHaveAttribute("aria-busy", "true");
    expect(spinner).toHaveAttribute("aria-label", "Loading");
    expect(spinner).toHaveAttribute("data-testid", "spinner");
  });

  it("accepts a custom label", () => {
    render(<Spinner label="Loading sessions" />);

    expect(screen.getByRole("status", { name: "Loading sessions" })).toBeInTheDocument();
  });
});
