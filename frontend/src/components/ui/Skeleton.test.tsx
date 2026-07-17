import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Skeleton } from "./Skeleton";

describe("Skeleton", () => {
  it("renders an aria-hidden placeholder with a testid", () => {
    render(<Skeleton />);

    const skeleton = screen.getByTestId("skeleton");
    expect(skeleton).toHaveAttribute("aria-hidden");
  });

  it("applies the text variant class by default", () => {
    render(<Skeleton />);

    expect(screen.getByTestId("skeleton").className).toContain("rounded");
  });

  it("applies the circle variant class", () => {
    render(<Skeleton variant="circle" />);

    expect(screen.getByTestId("skeleton").className).toContain("rounded-full");
  });

  it("applies the rect variant class", () => {
    render(<Skeleton variant="rect" />);

    expect(screen.getByTestId("skeleton").className).toContain("rounded-[var(--radius-card)]");
  });
});
