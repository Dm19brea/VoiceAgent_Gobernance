import Link from "next/link";

import { ReportView } from "@/components/ReportView";
import { TranscriptView } from "@/components/TranscriptView";

export default async function SessionReportPage({
  params,
}: Readonly<{ params: Promise<{ id: string }> }>) {
  const { id } = await params;

  return (
    <section>
      <Link href="/" className="text-sm text-muted transition-colors hover:text-foreground hover:underline">
        ← Sessions
      </Link>
      <div className="mt-2 rounded-[var(--radius-card)] bg-surface p-4 shadow-[var(--shadow-card)]">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Evaluation report
        </h1>
        <p className="mt-1 font-mono text-xs text-muted">{id}</p>
      </div>
      <div className="mt-6">
        <TranscriptView sessionId={id} />
      </div>
      <div className="mt-6">
        <ReportView sessionId={id} />
      </div>
    </section>
  );
}
