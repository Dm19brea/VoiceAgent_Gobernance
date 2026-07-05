"use client";

import { useEffect, useState } from "react";

import { wsBaseUrl } from "@/lib/api/config";
import type { ActiveSession } from "@/lib/api/types";

export function useActiveSessions(): ActiveSession[] {
  const [sessions, setSessions] = useState<ActiveSession[]>([]);

  useEffect(() => {
    const socket = new WebSocket(`${wsBaseUrl}/ws/active-sessions`);
    socket.onmessage = (event) => {
      try {
        setSessions(JSON.parse(event.data) as ActiveSession[]);
      } catch {
        // Ignore malformed frames; keep the last known state.
      }
    };
    return () => socket.close();
  }, []);

  return sessions;
}
