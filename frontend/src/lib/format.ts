/** Display formatting helpers shared by the dashboard views. */

/** Format a score with exactly two decimals; null renders as an em dash. */
export function formatScore(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

const dateTimeFormatter = new Intl.DateTimeFormat("es-ES", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Europe/Madrid",
});

/** Format an ISO UTC timestamp for display in Spanish locale, Madrid time. */
export function formatDateTime(iso: string): string {
  return dateTimeFormatter.format(new Date(iso));
}
