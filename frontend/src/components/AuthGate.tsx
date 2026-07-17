"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore, type ReactNode } from "react";

import { getAuthStatus } from "@/lib/api/client";
import { getToken } from "@/lib/auth/token";

// Routes that own their own auth flow: never gate them, or the redirect
// itself would render inside AuthGate again and loop forever.
const UNGATED_ROUTES = new Set(["/login", "/setup"]);

// `useSyncExternalStore` returns the server snapshot (`false`) during SSR and
// the first client render, then re-renders with the client snapshot (`true`)
// once hydrated — the React-sanctioned "is hydrated" signal, avoiding a
// setState-in-effect and any hydration mismatch. The auth token lives in
// `localStorage` (client-only), so it is only read after hydration; nothing
// mutates it outside our own login/logout navigation, so no subscription is
// needed.
const NO_SUBSCRIPTION = () => () => {};
const CLIENT_SNAPSHOT = () => true;
const SERVER_SNAPSHOT = () => false;

/**
 * Redirects an unauthenticated app load to `/setup` (first run) or `/login`
 * (already configured); renders `children` once a token is present or on
 * `/login`/`/setup` themselves.
 */
export function AuthGate({ children }: Readonly<{ children: ReactNode }>) {
  const router = useRouter();
  const pathname = usePathname();
  const hydrated = useSyncExternalStore(NO_SUBSCRIPTION, CLIENT_SNAPSHOT, SERVER_SNAPSHOT);

  const ungated = UNGATED_ROUTES.has(pathname);
  const authed = hydrated && getToken() !== null;
  const shouldGate = hydrated && !ungated && !authed;

  useEffect(() => {
    if (!shouldGate) return;

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
  }, [shouldGate, router]);

  if (ungated) return <>{children}</>;
  if (!authed) return null;
  return <>{children}</>;
}
