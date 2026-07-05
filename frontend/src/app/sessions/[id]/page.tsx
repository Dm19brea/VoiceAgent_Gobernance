import Link from "next/link";

import { ReportView } from "@/components/ReportView";

export default async function SessionReportPage({
  params,
}: Readonly<{ params: Promise<{ id: string }> }>) {
  const { id } = await params;

  return (
    <section>
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← Sessions
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Evaluation report</h1>
      <p className="mt-1 font-mono text-xs text-neutral-500">{id}</p>
      <div className="mt-6">
        <ReportView sessionId={id} />
      </div>
    </section>
  );
}
