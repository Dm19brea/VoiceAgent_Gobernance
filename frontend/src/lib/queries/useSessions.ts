import { useQuery } from "@tanstack/react-query";

import { getAgentSessions, getSessions } from "@/lib/api/client";

export function useSessions(agentId: string | null = null) {
  return useQuery({
    queryKey: ["sessions", agentId ?? "all"],
    queryFn: () => (agentId ? getAgentSessions(agentId) : getSessions()),
  });
}
