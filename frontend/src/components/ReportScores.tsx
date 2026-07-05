import type { Report, Scores } from "@/lib/api/types";

const DIMENSIONS: ReadonlyArray<readonly [label: string, key: keyof Scores]> = [
  ["Conversational", "conversational"],
  ["Operational", "operational"],
  ["Technical", "technical"],
  ["Risk", "risk"],
];

export function ReportScores({ report }: Readonly<{ report: Report }>) {
  return (
    <div className="space-y-6">
      <div className="flex items-baseline gap-4">
        <span className="text-4xl font-semibold tabular-nums">{report.score_global}</span>
        <span
          className={
            report.result === "passed"
              ? "rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800"
              : "rounded-full bg-red-100 px-3 py-1 text-sm font-medium text-red-800"
          }
        >
          {report.result}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {DIMENSIONS.map(([label, key]) => (
          <div key={key} className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-800">
            <dt className="text-xs text-neutral-500">{label}</dt>
            <dd className="mt-1 text-lg font-medium tabular-nums">{report.scores[key] ?? "—"}</dd>
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
