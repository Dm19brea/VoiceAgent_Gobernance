import type { ActiveSession } from "@/lib/api/types";

export function ActiveSessionsPanel({ sessions }: Readonly<{ sessions: ActiveSession[] }>) {
  return (
    <section aria-label="Active sessions">
      <div className="flex items-center gap-2">
        <span className="inline-block h-2 w-2 rounded-full bg-green-500" aria-hidden />
        <h2 className="text-sm font-medium text-neutral-600 dark:text-neutral-300">
          Active sessions
        </h2>
      </div>

      {sessions.length === 0 ? (
        <p className="mt-2 text-sm text-neutral-500">No active sessions.</p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm">
          {sessions.map((session) => (
            <li key={session.session_id} className="font-mono text-xs">
              {session.session_id}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
