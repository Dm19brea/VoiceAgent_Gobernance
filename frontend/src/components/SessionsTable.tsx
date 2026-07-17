import Link from "next/link";

import type { SessionSummary } from "@/lib/api/types";
import { formatDateTime, formatScore } from "@/lib/format";

import { StatusBadge } from "./ui/StatusBadge";

const HEADERS = ["Session", "Agent", "Status", "Result", "Score", "Started"];

export function SessionsTable({ sessions }: Readonly<{ sessions: SessionSummary[] }>) {
  if (sessions.length === 0) {
    return <p className="text-sm text-neutral-500">No sessions yet.</p>;
  }

  return (
    <table className="w-full border-collapse text-left text-sm">
      <thead>
        <tr className="border-b border-neutral-200 text-neutral-500 dark:border-neutral-800">
          {HEADERS.map((header) => (
            <th key={header} className="py-2 pr-4 font-medium">
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sessions.map((session) => (
          <tr
            key={session.session_id}
            className="border-b border-neutral-100 transition-colors hover:bg-surface-muted focus-within:bg-surface-muted dark:border-neutral-900"
          >
            <td className="py-2 pr-4 font-mono text-xs">
              <Link
                href={`/sessions/${session.session_id}`}
                className="rounded text-blue-600 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-current dark:text-blue-400"
              >
                {session.session_id}
              </Link>
            </td>
            <td className="py-2 pr-4">{session.agent_name}</td>
            <td className="py-2 pr-4">
              <StatusBadge status={session.status} />
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={session.result} />
            </td>
            <td className="py-2 pr-4 tabular-nums">{formatScore(session.score_global)}</td>
            <td className="py-2 pr-4 text-neutral-500">{formatDateTime(session.started_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
