import { useQuery } from "@tanstack/react-query";

import { ApiError, getReport } from "@/lib/api/client";

export function useReport(sessionId: string) {
  return useQuery({
    queryKey: ["report", sessionId],
    queryFn: () => getReport(sessionId),
    // A 404 means "not evaluated yet" — a normal state, not worth retrying.
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 404) && failureCount < 2,
  });
}
