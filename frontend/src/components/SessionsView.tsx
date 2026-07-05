"use client";

import { useSessions } from "@/lib/queries/useSessions";

import { SessionsTable } from "./SessionsTable";

export function SessionsView() {
  const { data, isPending, isError } = useSessions();

  if (isPending) {
    return <p className="text-sm text-neutral-500">Loading sessions…</p>;
  }

  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Couldn&apos;t load sessions.
      </p>
    );
  }

  return <SessionsTable sessions={data} />;
}
