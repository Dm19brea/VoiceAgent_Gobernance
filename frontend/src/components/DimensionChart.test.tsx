import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Scores } from "@/lib/api/types";

import { DimensionChart } from "./DimensionChart";

const scores: Scores = { conversational: 88, operational: null, technical: 74, risk: 70 };

describe("DimensionChart", () => {
  it("summarises each available dimension for accessibility", () => {
    render(<DimensionChart scores={scores} />);

    const chart = screen.getByRole("img");
    expect(chart).toHaveAccessibleName(/conversational 88/i);
    expect(chart).toHaveAccessibleName(/technical 74/i);
    expect(chart).toHaveAccessibleName(/risk 70/i);
  });

  it("excludes dimensions that have no score", () => {
    render(<DimensionChart scores={scores} />);

    expect(screen.getByRole("img")).not.toHaveAccessibleName(/operational/i);
  });
});
