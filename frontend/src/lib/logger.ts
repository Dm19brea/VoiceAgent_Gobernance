import pino from "pino";

export const logger = pino({
  level: process.env.NEXT_PUBLIC_LOG_LEVEL ?? "info",
  browser: { asObject: true },
});

/** Log a named client event with an error, without leaking payloads. */
export function logError(event: string, error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  logger.error({ event, error: message }, event);
}
