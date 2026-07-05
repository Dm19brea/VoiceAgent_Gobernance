"use client";

import { ApiError } from "@/lib/api/client";
import { useReport } from "@/lib/queries/useReport";

import { DimensionChart } from "./DimensionChart";
import { ReportScores } from "./ReportScores";

export function ReportView({ sessionId }: Readonly<{ sessionId: string }>) {
  const { data, isPending, isError, error } = useReport(sessionId);

  if (isPending) {
    return <p className="text-sm text-neutral-500">Loading report…</p>;
  }

  if (isError) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <p role="status" className="text-sm text-neutral-500">
          This session has not been evaluated yet.
        </p>
      );
    }
    return (
      <p role="alert" className="text-sm text-red-600">
        Couldn&apos;t load the report.
      </p>
    );
  }

  return (
    <div className="space-y-8">
      <ReportScores report={data} />
      <DimensionChart scores={data.scores} />
    </div>
  );
}
