import { describe, expect, it } from "vitest";

import { validatePassword } from "./passwordPolicy";

describe("validatePassword", () => {
  it("returns no violations for a fully compliant password", () => {
    expect(validatePassword("Correct-Horse9!")).toEqual([]);
  });

  it("flags a password shorter than 12 characters", () => {
    expect(validatePassword("Sh0rt!")).toContain("min_length");
  });

  it("flags a missing uppercase letter", () => {
    expect(validatePassword("lowercase-only9!")).toContain("uppercase");
  });

  it("flags a missing lowercase letter", () => {
    expect(validatePassword("UPPERCASE-ONLY9!")).toContain("lowercase");
  });

  it("flags a missing digit", () => {
    expect(validatePassword("NoDigitsHere!!")).toContain("digit");
  });

  it("flags a missing special character", () => {
    expect(validatePassword("NoSpecialChar9x")).toContain("special");
  });

  it("returns every unmet rule at once, not just the first", () => {
    const violations = validatePassword("short");
    expect(violations).toEqual(
      expect.arrayContaining(["min_length", "uppercase", "digit", "special"]),
    );
    expect(violations).not.toContain("lowercase");
  });
});
