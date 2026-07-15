import { useQuery } from "@tanstack/react-query";

import { ApiError, getSessionEvents } from "@/lib/api/client";

export function useSessionEvents(sessionId: string) {
  return useQuery({
    queryKey: ["session-events", sessionId],
    queryFn: () => getSessionEvents(sessionId),
    // A 404 means "not evaluated yet" — a normal state, not worth retrying.
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });
}
