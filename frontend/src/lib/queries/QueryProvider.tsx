"use client";

import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { logError } from "@/lib/logger";

export function QueryProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [client] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (error) => logError("query_failed", error),
        }),
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
