import type { Report, Scores } from "@/lib/api/types";
import { formatScore } from "@/lib/format";

import { ScoringHelpDialog } from "./ScoringHelpDialog";

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
      <div className="flex items-baseline gap-4">
        <span className="text-4xl font-semibold tabular-nums">
          {formatScore(report.score_global)}
        </span>
        <span
          className={
            report.result === "passed"
              ? "rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800"
              : "rounded-full bg-red-100 px-3 py-1 text-sm font-medium text-red-800"
          }
        >
          {report.result}
        </span>
        <ScoringHelpDialog />
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {DIMENSIONS.map(([label, key]) => (
          <div key={key} className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-800">
            <dt className="text-xs text-neutral-500">{label}</dt>
            <dd className="mt-1 text-lg font-medium tabular-nums">
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
