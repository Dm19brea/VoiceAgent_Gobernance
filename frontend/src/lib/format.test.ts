import { describe, expect, it } from "vitest";

import { formatDateTime, formatScore } from "./format";

describe("formatScore", () => {
  it("rounds to two decimals", () => {
    expect(formatScore(87.90123456790123)).toBe("87.90");
    expect(formatScore(99.48148148148148)).toBe("99.48");
  });

  it("keeps integers with two decimals for stable column width", () => {
    expect(formatScore(100)).toBe("100.00");
  });

  it("renders null as an em dash", () => {
    expect(formatScore(null)).toBe("—");
  });
});

describe("formatDateTime", () => {
  it("formats an ISO UTC timestamp in Spanish locale and Madrid time", () => {
    // 16:58 UTC = 18:58 in Europe/Madrid (CEST, summer)
    expect(formatDateTime("2026-07-16T16:58:52.005000Z")).toBe("16 jul 2026, 18:58");
  });

  it("handles winter time (CET)", () => {
    // 10:00 UTC = 11:00 in Europe/Madrid (CET)
    expect(formatDateTime("2026-01-15T10:00:00Z")).toBe("15 ene 2026, 11:00");
  });
});
