"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { getAuthStatus } from "@/lib/api/client";
import { getToken } from "@/lib/auth/token";

// Routes that own their own auth flow: never gate them, or the redirect
// itself would render inside AuthGate again and loop forever.
const UNGATED_ROUTES = new Set(["/login", "/setup"]);

/**
 * Redirects an unauthenticated app load to `/setup` (first run) or `/login`
 * (already configured); renders `children` once a token is present or on
 * `/login`/`/setup` themselves.
 */
export function AuthGate({ children }: Readonly<{ children: ReactNode }>) {
  const router = useRouter();
  const pathname = usePathname();
  const isGated = !UNGATED_ROUTES.has(pathname) && !getToken();

  useEffect(() => {
    if (!isGated) return;

    let cancelled = false;
    getAuthStatus()
      .then(({ needsSetup }) => {
        if (cancelled) return;
        router.replace(needsSetup ? "/setup" : "/login");
      })
      .catch(() => {
        if (cancelled) return;
        router.replace("/login");
      });

    return () => {
      cancelled = true;
    };
  }, [isGated, router]);

  if (isGated) return null;
  return <>{children}</>;
}
