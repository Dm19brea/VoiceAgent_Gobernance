import { describe, expect, it, vi } from "vitest";

import { logError, logger } from "./logger";

describe("logError", () => {
  it("logs the event name and the error message", () => {
    const spy = vi.spyOn(logger, "error").mockImplementation(() => undefined);

    logError("sessions_query_failed", new Error("boom"));

    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0]).toMatchObject({
      event: "sessions_query_failed",
      error: "boom",
    });

    spy.mockRestore();
  });

  it("stringifies non-Error values", () => {
    const spy = vi.spyOn(logger, "error").mockImplementation(() => undefined);

    logError("odd", "just a string");

    expect(spy.mock.calls[0][0]).toMatchObject({ event: "odd", error: "just a string" });

    spy.mockRestore();
  });
});
