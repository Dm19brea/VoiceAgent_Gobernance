"use client";

import { useActiveSessions } from "@/lib/queries/useActiveSessions";

import { ActiveSessionsPanel } from "./ActiveSessionsPanel";

export function ActiveSessionsLive() {
  const sessions = useActiveSessions();
  return <ActiveSessionsPanel sessions={sessions} />;
}
