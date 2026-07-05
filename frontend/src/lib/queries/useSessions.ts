import { useQuery } from "@tanstack/react-query";

import { getSessions } from "@/lib/api/client";

export function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: getSessions });
}
