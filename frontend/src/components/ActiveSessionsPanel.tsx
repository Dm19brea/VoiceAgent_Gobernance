import type { ActiveSession } from "@/lib/api/types";

const INTERRUPTION_WINDOW_MS = 4000;
// Tolerate a small client-behind-server clock skew so a slightly-negative
// elapsed time still counts as recent (otherwise the badge would never show).
const CLOCK_SKEW_TOLERANCE_MS = 2000;

function speakingLabel(role: ActiveSession["speaking_role"]): string {
  if (role === "agent") return "Agent speaking";
  if (role === "user") return "User speaking";
  return "Idle";
}

function speakingDotClassName(role: ActiveSession["speaking_role"]): string {
  if (role === "agent") return "bg-green-500 animate-pulse";
  if (role === "user") return "bg-blue-500 animate-pulse";
  return "bg-neutral-400";
}

function isRecentInterruption(lastInterruptionAt: string | null): boolean {
  if (lastInterruptionAt === null) return false;
  const elapsed = Date.now() - new Date(lastInterruptionAt).getTime();
  return elapsed >= -CLOCK_SKEW_TOLERANCE_MS && elapsed <= INTERRUPTION_WINDOW_MS;
}

export function ActiveSessionsPanel({ sessions }: Readonly<{ sessions: ActiveSession[] }>) {
  return (
    <section
      aria-label="Active sessions"
      className="rounded-[var(--radius-card)] bg-surface p-4 shadow-[var(--shadow-card)]"
    >
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full bg-success shadow-[var(--shadow-glow)] animate-[var(--animate-pulse-ring)]"
          aria-hidden
        />
        <h2 className="text-sm font-medium text-muted">Active sessions</h2>
      </div>

      {sessions.length === 0 ? (
        <p role="status" className="mt-2 text-sm text-muted">
          No active sessions.
        </p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm">
          {sessions.map((session) => (
            <li
              key={session.session_id}
              className="flex items-center gap-2 rounded-[var(--radius-card)] px-1 py-0.5 transition-colors hover:bg-surface-muted"
            >
              <span className="font-mono text-xs">{session.session_id}</span>
              <span className="flex items-center gap-1 text-xs text-muted">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${speakingDotClassName(session.speaking_role)}`}
                  aria-hidden
                />
                {speakingLabel(session.speaking_role)}
              </span>
              {isRecentInterruption(session.last_interruption_at) && (
                <span className="rounded-[var(--radius-badge)] bg-warning-surface px-1.5 py-0.5 text-xs font-medium text-warning-fg transition-colors">
                  User interrupted
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
