import type { Report, Scores } from "@/lib/api/types";
import { formatScore } from "@/lib/format";

import { ScoringHelpDialog } from "./ScoringHelpDialog";
import { StatusBadge } from "./ui/StatusBadge";

// Operational is intentionally omitted: the dimension is out of the MVP scope
// (no operational metrics exist, so it never scores).
const DIMENSIONS: ReadonlyArray<readonly [label: string, key: keyof Scores]> = [
  ["Conversational", "conversational"],
  ["Technical", "technical"],
  // The engine key stays "risk"; the label reads as safety because the score
  // is inverted-risk: 100 means no incidents were observed.
  ["Seguridad", "risk"],
];

export function ReportScores({ report }: Readonly<{ report: Report }>) {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline gap-4 rounded-[var(--radius-card)] bg-surface p-4 shadow-[var(--shadow-card)]">
        <span className="text-5xl font-bold tabular-nums text-brand">
          {formatScore(report.score_global)}
        </span>
        <StatusBadge status={report.result} />
        <ScoringHelpDialog />
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {DIMENSIONS.map(([label, key]) => (
          <div
            key={key}
            className="rounded-[var(--radius-card)] border border-border bg-surface p-3 shadow-[var(--shadow-card)]"
          >
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
              {formatScore(report.scores[key])}
            </dd>
          </div>
        ))}
      </dl>

      {report.blocking_flags.length > 0 && (
        <div>
          <h2 className="text-sm font-medium text-red-700">Blocking flags</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {report.blocking_flags.map((flag) => (
              <li key={flag.code}>
                <span className="font-mono text-xs">{flag.code}</span> — {flag.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
