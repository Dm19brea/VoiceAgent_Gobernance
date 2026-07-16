"use client";

import { useEffect, useState } from "react";

import { wsBaseUrl } from "@/lib/api/config";
import type { ActiveSession } from "@/lib/api/types";
import { getToken } from "@/lib/auth/token";

export function useActiveSessions(): ActiveSession[] {
  const [sessions, setSessions] = useState<ActiveSession[]>([]);

  useEffect(() => {
    const token = getToken();
    const query = token ? `?token=${encodeURIComponent(token)}` : "";
    const socket = new WebSocket(`${wsBaseUrl}/ws/active-sessions${query}`);
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
